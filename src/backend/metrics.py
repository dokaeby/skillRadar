"""수집 실행 품질 지표 — contextvar로 파이프라인 실행 단위로 집계한다.

metrics_scope() 안에서 실행된 LLM/캐시/검증 코드가 카운터를 자동 증가시키며,
스코프 밖(테스트, 단발 호출)에서는 모든 기록이 no-op이다.
집계 결과는 Snapshot.metrics_json에 저장돼 시계열 추적이 가능하다.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

from pydantic import BaseModel

CacheKind = Literal["classify", "summarize", "verify"]


class RunMetrics(BaseModel):
    """한 플랫폼 수집 실행의 LLM·캐시·검증 지표."""

    llm_calls: int = 0  # LLM HTTP 시도 총횟수 (재시도 포함)
    llm_retries: int = 0  # 첫 시도 이후 재시도 횟수
    llm_retry_successes: int = 0  # 재시도 끝에 성공한 호출 수
    verify_calls: int = 0  # judge 검증 호출 수
    verify_passed: int = 0  # 검증 통과 수
    summary_fallbacks: int = 0  # description 폴백으로 끝난 요약 수
    cache_hits_classify: int = 0
    cache_hits_summarize: int = 0
    cache_hits_verify: int = 0
    repos_processed: int = 0
    duration_ms: int = 0


_current: ContextVar[RunMetrics | None] = ContextVar(
    "skillradar_run_metrics", default=None
)


@contextmanager
def metrics_scope() -> Iterator[RunMetrics]:
    """실행 지표 수집 스코프. 이 안의 코드가 지표를 자동 기록한다.

    입력: 없음
    출력: yield RunMetrics — 스코프 종료 후에도 참조 가능
    결과: 컨텍스트 종료 시 contextvar 원복
    """
    metrics = RunMetrics()
    token = _current.set(metrics)
    try:
        yield metrics
    finally:
        _current.reset(token)


def _active() -> RunMetrics | None:
    """현재 스코프의 지표 객체. 스코프 밖이면 None."""
    return _current.get()


def record_llm_attempt(is_retry: bool) -> None:
    """LLM HTTP 시도 1회를 기록한다.

    입력: is_retry — 첫 시도가 아닌 재시도면 True
    출력: 없음
    결과: llm_calls(+1), 재시도면 llm_retries(+1)
    """
    m = _active()
    if m is None:
        return
    m.llm_calls += 1
    if is_retry:
        m.llm_retries += 1


def record_llm_success(was_retry: bool) -> None:
    """LLM 호출 성공을 기록한다. 재시도 끝 성공이면 retry_successes에 반영.

    입력: was_retry — 성공한 시도가 재시도였으면 True
    출력: 없음
    결과: was_retry면 llm_retry_successes(+1)
    """
    m = _active()
    if m is not None and was_retry:
        m.llm_retry_successes += 1


def record_verify(ok: bool) -> None:
    """judge 검증 호출 1회와 통과 여부를 기록한다.

    입력: ok — 검증 통과 여부
    출력: 없음
    결과: verify_calls(+1), 통과면 verify_passed(+1)
    """
    m = _active()
    if m is None:
        return
    m.verify_calls += 1
    if ok:
        m.verify_passed += 1


def record_fallback() -> None:
    """description 폴백 요약 사용을 기록한다.

    입력: 없음
    출력: 없음
    결과: summary_fallbacks(+1)
    """
    m = _active()
    if m is not None:
        m.summary_fallbacks += 1


def record_cache_hit(kind: CacheKind) -> None:
    """content_hash 캐시 히트를 기록한다.

    입력: kind — "classify"|"summarize"|"verify"
    출력: 없음
    결과: 해당 cache_hits_* 카운터(+1)
    """
    m = _active()
    if m is None:
        return
    if kind == "classify":
        m.cache_hits_classify += 1
    elif kind == "summarize":
        m.cache_hits_summarize += 1
    else:
        m.cache_hits_verify += 1


def record_repos(count: int) -> None:
    """처리된 repo 수를 기록한다.

    입력: count — 파이프라인이 처리한 repo 수
    출력: 없음
    결과: repos_processed = count
    """
    m = _active()
    if m is not None:
        m.repos_processed = count


def record_duration_ms(ms: int) -> None:
    """파이프라인 실행 시간을 기록한다.

    입력: ms — 경과 밀리초
    출력: 없음
    결과: duration_ms = ms
    """
    m = _active()
    if m is not None:
        m.duration_ms = ms


def metrics_dict(metrics: RunMetrics) -> dict[str, float | int | None]:
    """RunMetrics + 파생 지표를 JSON 저장용 dict로 변환한다.

    입력: metrics — 집계가 끝난 RunMetrics
    출력: dict — 카운터 필드 + retry_rate/retry_success_rate/
        unsupported_claim_rate/fidelity_score 파생 지표
    결과: 없음 (모델 → dict 변환)
    """
    data: dict[str, float | int | None] = metrics.model_dump()
    data["retry_rate"] = (
        round(metrics.llm_retries / metrics.llm_calls, 4)
        if metrics.llm_calls
        else None
    )
    data["retry_success_rate"] = (
        round(metrics.llm_retry_successes / metrics.llm_retries, 4)
        if metrics.llm_retries
        else None
    )
    data["unsupported_claim_rate"] = (
        round((metrics.verify_calls - metrics.verify_passed) / metrics.verify_calls, 4)
        if metrics.verify_calls
        else None
    )
    data["fidelity_score"] = (
        round(metrics.verify_passed / metrics.verify_calls, 4)
        if metrics.verify_calls
        else None
    )
    return data


__all__ = [
    "CacheKind",
    "RunMetrics",
    "metrics_dict",
    "metrics_scope",
    "record_cache_hit",
    "record_duration_ms",
    "record_fallback",
    "record_llm_attempt",
    "record_llm_success",
    "record_repos",
    "record_verify",
]

