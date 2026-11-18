"""수집 파이프라인: GitHub 검색 → dedupe → README → LLM 요약 → DB 저장."""

import asyncio
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.github_client import GitHubClient, RepoHit, stars_delta, today_kst
from backend.models import Snapshot, SnapshotItem
from backend.summarizer import (
    Summarizer,
    content_hash,
    fallback_summaries,
    fallback_summaries_async,
)

logger = logging.getLogger(__name__)

TOP_N = 10
README_CONCURRENCY = 5


async def collect_platform(
    platform: str,
    session: Session,
    settings: Settings,
    github: GitHubClient | None = None,
    summarizer: Summarizer | None = None,
    collected_date: date | None = None,
) -> Snapshot:
    """플랫폼 하나를 수집해 스냅샷으로 저장한다.

    이미 같은 날짜 스냅샷이 있으면 항목을 교체(멱등 재수집)한다.
    개별 항목의 LLM/README 실패는 해당 항목만 폴백 처리하고 수집은 계속한다.
    """
    gh = github or GitHubClient(token=settings.github_token.get_secret_value())
    sm = summarizer or (
        Summarizer(
            api_key=settings.llm_api_key.get_secret_value(),
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            min_interval=4.0,  # LLM rate limit 대응 호출 간격
        )
        if settings.llm_enabled
        else None
    )
    own_gh = github is None
    own_sm = summarizer is None and sm is not None
    try:
        # 1) 플랫폼 쿼리들을 합쳐 중복 제거 후 star 순 Top N 선정
        queries = settings.platform_queries().get(platform, [])
        merged: dict[str, RepoHit] = {}
        for q in queries:
            for hit in await gh.search_repositories(q):
                if hit.archived or hit.fork:
                    continue
                prev = merged.get(hit.full_name)
                if prev is None or hit.stars > prev.stars:
                    merged[hit.full_name] = hit
        ranked = sorted(merged.values(), key=lambda h: h.stars, reverse=True)[:TOP_N]

        # 2) 직전 스냅샷의 star 수 (오늘 증가량 계산용)
        collected = collected_date or date.fromisoformat(today_kst())
        prev_stars = _previous_stars(session, platform, collected)

        # 3) 기존 스냅샷 재수집이면 삭제 후 재생성 (멱등)
        existing = session.execute(
            select(Snapshot).where(
                Snapshot.platform == platform, Snapshot.collected_date == collected
            )
        ).scalar_one_or_none()
        if existing:
            session.delete(existing)
            session.flush()

        snapshot = Snapshot(platform=platform, collected_date=collected)
        session.add(snapshot)
        session.flush()

        # 4) README + 요약 (항목별 독립 처리, 동시성 제한)
        sem = asyncio.Semaphore(README_CONCURRENCY)

        async def fallback_for(hit: RepoHit) -> tuple[list[str], list[str], list[str]]:
            if settings.translate_fallback:
                fb = await fallback_summaries_async(hit.description, hit.full_name)
            else:
                fb = fallback_summaries(hit.description, hit.full_name)
            return fb["en"], fb["zh"], fb["ko"]

        async def process(idx: int, hit: RepoHit) -> SnapshotItem:
            async with sem:
                readme = await gh.fetch_readme(hit.full_name)
            chash = content_hash(hit.description, readme)
            cached = _find_cached_summary(session, hit.full_name, chash)
            if cached:
                en, zh, ko = cached
            elif sm is not None:
                try:
                    result = await sm.summarize(
                            platform, hit.full_name, hit.description, readme
                        )
                    en, zh, ko = result["en"], result["zh"], result["ko"]
                except Exception as exc:  # noqa: BLE001
                    logger.warning("요약 실패 %s: %s", hit.full_name, exc)
                    en, zh, ko = await fallback_for(hit)
            else:
                en, zh, ko = await fallback_for(hit)
            return SnapshotItem(
                snapshot_id=snapshot.id,
                rank=idx + 1,
                repo_full_name=hit.full_name,
                repo_url=hit.html_url,
                description=hit.description,
                stars=hit.stars,
                language=hit.language,
                topics=hit.topics,
                readme_excerpt=readme[:3000] or None,
                summary_en=en,
                summary_zh=zh,
                summary_ko=ko,
                content_hash=chash,
                stars_today=stars_delta(hit.stars, prev_stars.get(hit.full_name)),
            )

        items = await asyncio.gather(*(process(i, h) for i, h in enumerate(ranked)))
        for item in items:
            session.add(item)
        session.commit()
        logger.info("%s %s 수집 완료: %d개", platform, collected, len(items))
        return snapshot
    except Exception:
        session.rollback()
        raise
    finally:
        if own_gh:
            await gh.aclose()
        if own_sm and sm is not None:
            await sm.aclose()


async def collect_all(
    session: Session,
    settings: Settings,
    platforms: tuple[str, ...] = ("claude", "chatgpt", "gemini"),
) -> list[Snapshot]:
    """전체 플랫폼 수집. 한 플랫폼 실패가 다른 플랫폼을 막지 않는다."""
    results: list[Snapshot] = []
    for platform in platforms:
        try:
            results.append(await collect_platform(platform, session, settings))
        except Exception as exc:  # noqa: BLE001 - 플랫폼별 격리
            logger.exception("%s 수집 실패: %s", platform, exc)
            session.rollback()
    return results


def _previous_stars(
    session: Session, platform: str, collected: date
) -> dict[str, int]:
    """가장 최근 이전 스냅샷의 repo→stars 맵."""
    snap = session.execute(
        select(Snapshot)
        .where(Snapshot.platform == platform, Snapshot.collected_date < collected)
        .order_by(Snapshot.collected_date.desc())
        .limit(1)
    ).scalar_one_or_none()
    if snap is None:
        return {}
    return {item.repo_full_name: item.stars for item in snap.items}


def _find_cached_summary(
    session: Session, full_name: str, chash: str
) -> tuple[list[str], list[str], list[str]] | None:
    """같은 repo+같은 content_hash의 이전 요약이 있으면 재사용한다."""
    row = session.execute(
        select(SnapshotItem)
        .where(SnapshotItem.repo_full_name == full_name, SnapshotItem.content_hash == chash)
        .where(SnapshotItem.summary_en.is_not(None))
        .order_by(SnapshotItem.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None or row.summary_en is None or row.summary_zh is None or row.summary_ko is None:
        return None
    return row.summary_en, row.summary_zh, row.summary_ko
