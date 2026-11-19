"""수집 파이프라인: LangGraph 큐레이터 실행 → 스냅샷 저장."""

import asyncio
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.config import Settings
from backend.github_client import GitHubClient, stars_delta, today_kst
from backend.graph.pipeline import run_platform_pipeline
from backend.models import Snapshot, SnapshotItem
from backend.schemas import CachedRepo, GitHubLike, SummarizerLike
from backend.summarizer import Summarizer, content_hash

logger = logging.getLogger(__name__)


async def collect_platform(
    platform: str,
    session: Session,
    settings: Settings,
    github: GitHubLike | None = None,
    summarizer: SummarizerLike | None = None,
    collected_date: date | None = None,
    force: bool = False,
) -> Snapshot:
    """플랫폼 하나를 수집해 스냅샷으로 저장한다.

    입력:
      - platform: str
      - session: Session
      - settings: Settings
      - github: GitHubLike | None
      - summarizer: SummarizerLike | None
      - collected_date: date | None
      - force: bool — True면 같은 날짜 기존 스냅샷이 있어도 재수집
    출력: Snapshot
    결과: Snapshot을 DB에 저장(멱등 upsert). 반환값은 저장된 Snapshot
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
        collected = collected_date or date.fromisoformat(today_kst())
        # 같은 날짜 스냅샷이 이미 있으면 재수집하지 않는다 (cron 중복 실행 방지).
        # force=True(수동 refresh)면 기존 스냅샷을 삭제하고 다시 수집한다.
        existing = session.execute(
            select(Snapshot).where(
                Snapshot.platform == platform, Snapshot.collected_date == collected
            )
        ).scalar_one_or_none()
        if existing is not None and not force:
            logger.info("%s %s 이미 수집됨 — 스킵", platform, collected)
            return existing

        # 1) LangGraph 큐레이터 파이프라인 실행
        #    (collect→dedupe→sanitize→classify→summarize→verify→rank)
        queries = settings.platform_queries().get(platform, [])

        async def _repo_cache(
            full_name: str, description: str | None, readme: str
        ) -> CachedRepo | None:
            """동일 content_hash의 이전 수집 레코드를 DB에서 조회한다.

            입력:
              - full_name: str
              - description: str | None
              - readme: str
            출력: CachedRepo — 요약 3개 언어 + taxonomy + 상태, 미스 시 None
            결과: 히트 시 LLM 분류·요약·검증 호출을 건너뛴다
            """
            row = _find_cached_repo(
                session, full_name, content_hash(description, readme)
            )
            if row is None:
                return None
            return {
                "en": row.summary_en,
                "zh": row.summary_zh,
                "ko": row.summary_ko,
                "taxonomy": row.taxonomy,
                "confidence": row.taxonomy_confidence,
                "status": row.summary_status,
            }

        state = await run_platform_pipeline(
            platform, queries, settings, github=gh, summarizer=sm,
            repo_cache=_repo_cache,
        )
        ranked_repos = state.ranked

        # 2) 직전 스냅샷의 star 수 (오늘 증가량 계산용)
        prev_stars = _previous_stars(session, platform, collected)

        # 3) force 재수집이면 기존 스냅샷 삭제 후 재생성 (멱등)
        if existing is not None:
            session.delete(existing)
            session.flush()

        snapshot = Snapshot(platform=platform, collected_date=collected)
        session.add(snapshot)
        session.flush()

        # 4) 요약 캐시 확인 후 SnapshotItem 생성
        items: list[SnapshotItem] = []
        for idx, rr in enumerate(ranked_repos):
            hit = rr.clean.repo
            summ = rr.summary
            chash = content_hash(hit.description, rr.clean.sanitized_readme)
            row = _find_cached_repo(session, hit.full_name, chash)
            if row is not None:
                en, zh, ko = row.summary_en, row.summary_zh, row.summary_ko
            else:
                en, zh, ko = summ.en, summ.zh, summ.ko
            items.append(
                SnapshotItem(
                    snapshot_id=snapshot.id,
                    rank=idx + 1,
                    repo_full_name=hit.full_name,
                    repo_url=hit.html_url,
                    description=hit.description,
                    stars=hit.stars,
                    language=hit.language,
                    topics=hit.topics,
                    readme_excerpt=(rr.clean.sanitized_readme or rr.clean.readme)[:3000] or None,
                    summary_en=en or None,
                    summary_zh=zh or None,
                    summary_ko=ko or None,
                    content_hash=chash,
                    stars_today=stars_delta(hit.stars, prev_stars.get(hit.full_name)),
                    license=hit.license,
                    taxonomy=rr.classification.label,
                    taxonomy_confidence=rr.classification.confidence,
                    rank_score=rr.rank_score,
                    summary_status=summ.status,
                )
            )
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
    session_factory: sessionmaker[Session],
    settings: Settings,
    platforms: tuple[str, ...] = ("claude", "chatgpt", "gemini"),
    force: bool = False,
) -> list[Snapshot]:
    """플랫폼별 수집을 병렬 실행한다. 플랫폼마다 독립 세션을 쓴다.

    입력:
      - session_factory: sessionmaker[Session]
      - settings: Settings
      - platforms: tuple[str, ...]
      - force: bool — True면 같은 날짜 기존 스냅샷 무시하고 재수집
    출력: list[Snapshot]
    결과: 플랫폼을 gather로 병렬 수집. 실패한 플랫폼은 건너뛰고 성공분만 반환
    """

    async def _one(platform: str) -> Snapshot | None:
        """

        입력:
          - platform: str
        출력: Snapshot | None
        결과: 수집 성공 시 Snapshot, 실패 시 None (플랫폼 격리)
        """
        session = session_factory()
        try:
            return await collect_platform(platform, session, settings, force=force)
        except Exception as exc:  # noqa: BLE001 - 플랫폼별 격리
            logger.exception("%s 수집 실패: %s", platform, exc)
            session.rollback()
            return None
        finally:
            session.close()

    results = await asyncio.gather(*(_one(p) for p in platforms))
    return [r for r in results if r is not None]


def _previous_stars(
    session: Session, platform: str, collected: date
) -> dict[str, int]:
    """가장 최근 이전 스냅샷의 repo→stars 맵.

    입력:
      - session: Session
      - platform: str
      - collected: date
    출력: dict[str, int]
    결과: 없음 (DB 읽기)
    """
    snap = session.execute(
        select(Snapshot)
        .where(Snapshot.platform == platform, Snapshot.collected_date < collected)
        .order_by(Snapshot.collected_date.desc())
        .limit(1)
    ).scalar_one_or_none()
    if snap is None:
        return {}
    return {item.repo_full_name: item.stars for item in snap.items}


def _find_cached_repo(session: Session, full_name: str, chash: str) -> SnapshotItem | None:
    """같은 repo+같은 content_hash의 이전 수집 레코드를 반환한다.

    입력:
      - session: Session
      - full_name: str
      - chash: str
    출력: SnapshotItem | None — 3개 언어 요약이 모두 있는 최신 행
    결과: content_hash 기반 캐시 조회 (분류·요약·검증 재사용)
    """
    row = session.execute(
        select(SnapshotItem)
        .where(SnapshotItem.repo_full_name == full_name, SnapshotItem.content_hash == chash)
        .where(SnapshotItem.summary_en.is_not(None))
        .order_by(SnapshotItem.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None or row.summary_en is None or row.summary_zh is None or row.summary_ko is None:
        return None
    return row
