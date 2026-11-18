"""큐레이터 StateGraph 노드 함수.

각 노드는 state를 받아 갱신 dict를 반환한다(langgraph 스타일).
외부 의존성(Settings/GitHubClient/Summarizer)은 configure_runtime()으로
주입하며, 미주입 시 get_settings()와 새 클라이언트로 폴백한다.
"""

import asyncio
import inspect
import logging
import math
from typing import Any

from backend.config import Settings, get_settings
from backend.github_client import GitHubClient, RepoHit
from backend.schemas import (
    GitHubLike,
    SummarizerLike,
    Classification,
    RankedRepo,
    RelatedTopic,
    RepoClean,
    RepoRaw,
    SummaryResult,
)
from backend.summarizer import (
    Summarizer,
    fallback_summaries_async,
    sanitize_readme,
)

logger = logging.getLogger(__name__)

_TOP_K = 10  # LLM 호출 비용 절약: 분류·요약·검증은 Top10만
_FINAL_TOP_N = 10
_MAX_RETRIES = 2

_settings_override: Settings | None = None
_github_override: GitHubLike | None = None
_summarizer_override: SummarizerLike | None = None
_summary_cache_override: Any = None


def configure_runtime(
    settings: Settings | None = None,
    github: GitHubLike | None = None,
    summarizer: SummarizerLike | None = None,
    summary_cache: Any = None,
) -> None:
    """run_platform_pipeline이 호출해 노드 의존성을 주입한다.

    summary_cache: async (full_name, description, sanitized_readme) ->
    SummaryResult | dict | tuple | None — 히트 시 LLM 호출을 건너뛴다.
    """
    global _settings_override, _github_override, _summarizer_override, _summary_cache_override
    _settings_override = settings
    _github_override = github
    _summarizer_override = summarizer
    _summary_cache_override = summary_cache


def reset_runtime() -> None:
    configure_runtime()


def _settings() -> Settings:
    return _settings_override or get_settings()


def _state_get(state: Any, key: str, default: Any = None) -> Any:
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _hit_to_raw(hit: RepoHit) -> RepoRaw:
    return RepoRaw(
        full_name=hit.full_name,
        html_url=hit.html_url,
        description=hit.description,
        stars=hit.stars,
        language=hit.language,
        topics=list(hit.topics),
        archived=hit.archived,
        fork=hit.fork,
        license=hit.license,
    )


def _summarizer(settings: Settings) -> SummarizerLike:
    if _summarizer_override is not None:
        return _summarizer_override
    return Summarizer(
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )


async def collect(state: Any) -> dict[str, Any]:
    """queries로 GitHub 검색 → RepoRaw 수집. full_name 중복은 stars 최대값 유지."""
    errors = list(_state_get(state, "errors", []) or [])
    queries = list(_state_get(state, "queries", []) or [])
    settings = _settings()

    shared = _state_get(state, "github") or _github_override
    client = shared if shared is not None else None
    owns_client = client is None
    if client is None:
        client = GitHubClient(token=settings.github_token.get_secret_value())

    best: dict[str, RepoRaw] = {}
    try:
        for query in queries:
            try:
                hits = await client.search_repositories(query)
            except Exception as exc:  # noqa: BLE001 - 쿼리 실패가 수집 전체를 막지 않게
                logger.warning("검색 실패 %r: %s", query, exc)
                errors.append(f"collect:{query}: {exc}")
                continue
            for hit in hits:
                raw = _hit_to_raw(hit)
                prev = best.get(raw.full_name)
                if prev is None or raw.stars > prev.stars:
                    best[raw.full_name] = raw
    finally:
        if owns_client:
            await client.aclose()

    logger.info("collect: %d repos from %d queries", len(best), len(queries))
    return {"repos_raw": list(best.values()), "errors": errors}


async def dedupe_filter(state: Any) -> dict[str, Any]:
    """archived/fork 제외 + stars 상위 10개만 유지 (_TOP_K)."""
    repos: list[RepoRaw] = list(_state_get(state, "repos_raw", []) or [])
    before = len(repos)
    kept = [r for r in repos if not (r.archived or r.fork)]
    excluded = before - len(kept)
    kept.sort(key=lambda r: r.stars, reverse=True)
    kept = kept[:_TOP_K]
    logger.info(
        "dedupe_filter: %d -> %d (archived/fork 제외 %d)", before, len(kept), excluded
    )
    return {"repos_raw": kept}


async def sanitize(state: Any) -> dict[str, Any]:
    """각 repo의 README를 가져와 정제. 동시성 5, 노드당 GitHubClient 1개."""
    repos: list[RepoRaw] = list(_state_get(state, "repos_raw", []) or [])
    errors = list(_state_get(state, "errors", []) or [])
    settings = _settings()

    shared = _state_get(state, "github") or _github_override
    client = shared if shared is not None else None
    owns_client = client is None
    if client is None:
        client = GitHubClient(token=settings.github_token.get_secret_value())

    sem = asyncio.Semaphore(5)

    async def _one(repo: RepoRaw) -> RepoClean:
        async with sem:
            try:
                raw = await client.fetch_readme(repo.full_name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("README 실패 %s: %s", repo.full_name, exc)
                errors.append(f"sanitize:{repo.full_name}: {exc}")
                raw = ""
            return RepoClean(
                repo=repo,
                readme=raw[:3000],
                sanitized_readme=sanitize_readme(raw),
            )

    try:
        clean = await asyncio.gather(*(_one(r) for r in repos))
    finally:
        if owns_client:
            await client.aclose()

    logger.info("sanitize: %d repos", len(clean))
    return {"repos_clean": list(clean), "errors": errors}


async def _classify_repo(clean: RepoClean, settings: Settings) -> Classification:
    from backend import llm_tasks  # 지연 임포트: 통합 전에도 그래프 구성 가능

    return await llm_tasks.classify_repo(
        description=clean.repo.description or "",
        readme=clean.sanitized_readme,
        name=clean.repo.full_name,
        topics=list(clean.repo.topics),
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_base_url,
        model=settings.judge_model,
    )


async def classify(state: Any) -> dict[str, Any]:
    """taxonomy 분류. LLM 비활성 시 전부 other/0.0."""
    cleans: list[RepoClean] = list(_state_get(state, "repos_clean", []) or [])
    prev: dict[str, Classification] = dict(
        _state_get(state, "classifications", {}) or {}
    )
    errors = list(_state_get(state, "errors", []) or [])
    settings = _settings()

    if not settings.llm_enabled:
        for clean in cleans:
            prev[clean.repo.full_name] = Classification(label="other", confidence=0.0)
        return {"classifications": prev}

    sem = asyncio.Semaphore(4)

    async def _one(clean: RepoClean) -> tuple[str, Classification | None]:
        async with sem:
            try:
                cls = await _classify_repo(clean, settings)
                return clean.repo.full_name, cls
            except Exception as exc:  # noqa: BLE001
                logger.warning("classify 실패 %s: %s", clean.repo.full_name, exc)
                errors.append(f"classify:{clean.repo.full_name}: {exc}")
                return clean.repo.full_name, None

    results = await asyncio.gather(*(_one(c) for c in cleans))
    for name, cls in results:
        if cls is not None:
            prev[name] = cls
    logger.info("classify: %d repos", len(prev))
    return {"classifications": prev, "errors": errors}


async def _summarize_one(
    summarizer: SummarizerLike, platform: str, clean: RepoClean
) -> SummaryResult:
    try:
        data = await summarizer.summarize(
            platform,
            clean.repo.full_name,
            clean.repo.description,
            clean.sanitized_readme,
        )
        return SummaryResult(status="ok", **data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("summarize 실패 %s: %s", clean.repo.full_name, exc)
        fb = await fallback_summaries_async(clean.repo.description, clean.repo.full_name)
        return SummaryResult(status="failed", **fb)


async def summarize(state: Any) -> dict[str, Any]:
    """repo별 3개 언어 요약 생성. 실패 시 폴백 + status='failed'."""
    cleans: list[RepoClean] = list(_state_get(state, "repos_clean", []) or [])
    prev: dict[str, SummaryResult] = dict(_state_get(state, "summaries", {}) or {})
    errors = list(_state_get(state, "errors", []) or [])
    platform = str(_state_get(state, "platform", "claude") or "claude")
    summarizer = _summarizer(_settings())

    sem = asyncio.Semaphore(5)

    def _cached_result(cached: Any) -> SummaryResult | None:
        if cached is None:
            return None
        if isinstance(cached, SummaryResult):
            return cached
        try:
            if isinstance(cached, dict):
                return SummaryResult(status="ok", **cached)
            en, zh, ko = cached
            return SummaryResult(status="ok", en=list(en), zh=list(zh), ko=list(ko))
        except Exception:
            return None

    async def _one(clean: RepoClean) -> tuple[str, SummaryResult]:
        async with sem:
            try:
                if _summary_cache_override is not None:
                    try:
                        cached = _summary_cache_override(
                            clean.repo.full_name,
                            clean.repo.description,
                            clean.sanitized_readme,
                        )
                        if inspect.isawaitable(cached):
                            cached = await cached
                        hit = _cached_result(cached)
                        if hit is not None:
                            return clean.repo.full_name, hit
                    except Exception as exc:  # noqa: BLE001 - 캐시 실패는 LLM 호출로 진행
                        logger.warning("summary cache 조회 실패 %s: %s", clean.repo.full_name, exc)
                return clean.repo.full_name, await _summarize_one(
                    summarizer, platform, clean
                )
            except Exception as exc:  # noqa: BLE001 - _summarize_one이 이미 폴백하지만 최종 방어
                logger.warning("summarize 최종 실패 %s: %s", clean.repo.full_name, exc)
                errors.append(f"summarize:{clean.repo.full_name}: {exc}")
                fb = await fallback_summaries_async(
                    clean.repo.description, clean.repo.full_name
                )
                return clean.repo.full_name, SummaryResult(status="failed", **fb)

    results = await asyncio.gather(*(_one(c) for c in cleans))
    for name, summary in results:
        prev[name] = summary
    logger.info("summarize: %d repos", len(prev))
    return {"summaries": prev, "errors": errors}


async def _verify_summary(
    clean: RepoClean, summary: SummaryResult, settings: Settings
) -> bool:
    from backend import llm_tasks

    return await llm_tasks.verify_summary(
        readme=clean.sanitized_readme,
        summary_lines=summary.en,
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_base_url,
        model=settings.judge_model,
    )


async def verify(state: Any) -> dict[str, Any]:
    """요약 충실도 검증. 실패 시 재요약 최대 2회, 초과 시 status='unverified'."""
    cleans: list[RepoClean] = list(_state_get(state, "repos_clean", []) or [])
    summaries: dict[str, SummaryResult] = dict(_state_get(state, "summaries", {}) or {})
    retries: dict[str, int] = dict(_state_get(state, "retries", {}) or {})
    errors = list(_state_get(state, "errors", []) or [])
    settings = _settings()

    if not settings.llm_enabled:
        return {"summaries": summaries, "retries": retries}

    by_name = {c.repo.full_name: c for c in cleans}
    platform = str(_state_get(state, "platform", "claude") or "claude")
    summarizer = _summarizer(settings)
    sem = asyncio.Semaphore(4)

    async def _one(clean: RepoClean) -> None:
        name = clean.repo.full_name
        summary = summaries.get(name)
        if summary is None:
            return
        try:
            async with sem:
                try:
                    ok = await _verify_summary(clean, summary, settings)
                except Exception as exc:  # noqa: BLE001 - 검증 실패는 재시도 대상
                    logger.warning("verify 실패 %s: %s", name, exc)
                    errors.append(f"verify:{name}: {exc}")
                    ok = False
            while not ok and retries.get(name, 0) < _MAX_RETRIES:
                retries[name] = retries.get(name, 0) + 1
                summary = await _summarize_one(summarizer, platform, clean)
                summaries[name] = summary
                try:
                    async with sem:
                        ok = await _verify_summary(clean, summary, settings)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("verify 재시도 실패 %s: %s", name, exc)
                    errors.append(f"verify:{name}: {exc}")
                    ok = False
            if not ok:
                summary.status = "unverified"
                summaries[name] = summary
        except Exception as exc:  # noqa: BLE001
            logger.warning("verify 노드 실패 %s: %s", name, exc)
            errors.append(f"verify:{name}: {exc}")

    await asyncio.gather(*(_one(c) for c in cleans))
    logger.info("verify: %d repos", len(summaries))
    return {"summaries": summaries, "retries": retries, "errors": errors}


async def rank(state: Any) -> dict[str, Any]:
    """rank_score 계산 후 상위 10개를 ranked에 저장."""
    cleans: list[RepoClean] = list(_state_get(state, "repos_clean", []) or [])
    summaries: dict[str, SummaryResult] = dict(_state_get(state, "summaries", {}) or {})
    classifications: dict[str, Classification] = dict(
        _state_get(state, "classifications", {}) or {}
    )

    ranked: list[RankedRepo] = []
    for clean in cleans:
        name = clean.repo.full_name
        summary = summaries.get(name)
        if summary is None:
            continue
        cls = classifications.get(name, Classification())
        stars = max(clean.repo.stars, 0)
        score = round(
            math.log10(stars + 1) * 20
            + (5.0 if summary.status == "ok" else 0.0)
            + cls.confidence * 5.0,
            2,
        )
        ranked.append(
            RankedRepo(
                clean=clean,
                classification=cls,
                summary=summary,
                rank_score=score,
            )
        )
    ranked.sort(key=lambda r: r.rank_score, reverse=True)
    top = ranked[:_FINAL_TOP_N]
    logger.info("rank: %d repos -> top %d", len(ranked), len(top))
    return {"ranked": top}


async def related(state: Any) -> dict[str, Any]:
    """토픽 공기반 관련 주제. 같은 스냅샷 내 repo 토픽 교집합, LLM 호출 없음."""
    cleans: list[RepoClean] = list(_state_get(state, "repos_clean", []) or [])

    topic_repos: dict[str, list[str]] = {}
    for clean in cleans:
        for topic in clean.repo.topics:
            topic_repos.setdefault(topic, []).append(clean.repo.full_name)

    related_topics: dict[str, list[RelatedTopic]] = {}
    for topic, repos in topic_repos.items():
        if len(repos) < 2:
            continue
        co_counts: dict[str, int] = {}
        repo_set = set(repos)
        for other, other_repos in topic_repos.items():
            if other == topic:
                continue
            score = len(repo_set & set(other_repos))
            if score > 0:
                co_counts[other] = score
        ranked = sorted(co_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        related_topics[topic] = [
            RelatedTopic(topic=t, score=float(s)) for t, s in ranked
        ]

    logger.info("related: %d topics", len(related_topics))
    return {"related_topics": related_topics}
