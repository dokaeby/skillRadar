"""Langfuse LLM 관측성 — API 키가 없으면 모든 span이 no-op.

Langfuse Cloud 무료 티어 사용. LANGFUSE_PUBLIC_KEY/SECRET_KEY가
설정된 경우에만 LLM 호출(classify/verify/summarize)을 generation
span으로 기록한다. 입력 프롬프트와 출력은 잘라서 보낸다.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

logger = logging.getLogger(__name__)

_client: Any = None
_tried = False
_MAX_FIELD = 4000  # 프롬프트/출력 필드 최대 길이


def _get_client() -> Any:
    """Langfuse 클라이언트를 지연 초기화한다. 키 없으면 None.

    입력: 없음 (get_settings()의 langfuse_* 필드 사용)
    출력: Langfuse 클라이언트 또는 None
    결과: 최초 호출 시 1회만 초기화 시도, 이후 캐시
    """
    global _client, _tried
    if _tried:
        return _client
    _tried = True
    try:
        from backend.config import get_settings

        settings = get_settings()
        public_key = settings.langfuse_public_key.get_secret_value()
        secret_key = settings.langfuse_secret_key.get_secret_value()
        if not (public_key and secret_key):
            return None
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=settings.langfuse_host,
        )
        logger.info("Langfuse tracing 활성화: %s", settings.langfuse_host)
    except Exception as exc:  # noqa: BLE001 - 관측성 실패가 수집을 막으면 안 됨
        logger.warning("Langfuse 초기화 실패 (tracing 비활성): %s", exc)
        _client = None
    return _client


def tracing_enabled() -> bool:
    """Langfuse 클라이언트가 초기화됐는지 반환한다.

    입력: 없음
    출력: bool
    결과: _get_client() 호출 부작용으로 초기화 트리거 가능
    """
    return _get_client() is not None


def _clip(value: Any) -> Any:
    """길이 제한: 문자열은 4000자로 자른다.

    입력: 임의 값
    출력: 자른 값 (문자열 아니면 그대로)
    결과: 없음
    """
    if isinstance(value, str) and len(value) > _MAX_FIELD:
        return value[:_MAX_FIELD] + "…[truncated]"
    return value


@contextmanager
def llm_span(
    name: str,
    *,
    model: str,
    input_text: str = "",
    metadata: dict[str, Any] | None = None,
) -> Iterator[Any | None]:
    """LLM 호출 1회를 Langfuse generation span으로 감싼다.

    입력:
      - name: str — span 이름 (예: "llm.classify", "llm.summarize")
      - model: str — 사용 모델명
      - input_text: str — 프롬프트 (4000자로 잘림)
      - metadata: dict — repo명, platform 등 부가 정보
    출력: yield observation 또는 None (tracing 비활성/실패 시)
    결과: 예외 발생 시 span을 ERROR로 마킹 후 재발생
    """
    client = _get_client()
    if client is None:
        yield None
        return
    try:
        cm = client.start_as_current_observation(
            as_type="generation",
            name=name,
            model=model,
            input=_clip(input_text),
            metadata=metadata or {},
        )
    except Exception as exc:  # noqa: BLE001 - span 생성 실패는 무시
        logger.debug("Langfuse span 생성 실패: %s", exc)
        yield None
        return
    try:
        obs = cm.__enter__()
    except Exception as exc:  # noqa: BLE001 - span 진입 실패는 관측성 문제일 뿐
        logger.debug("Langfuse span 진입 실패: %s", exc)
        yield None
        return
    import sys as _sys

    exc_info = None
    try:
        yield obs
    except Exception as exc:
        exc_info = _sys.exc_info()
        with suppress(Exception):
            obs.update(level="ERROR", status_message=str(exc)[:500])
        raise
    finally:
        with suppress(Exception):
            cm.__exit__(*exc_info) if exc_info else cm.__exit__(None, None, None)


@contextmanager
def trace_span(name: str, *, metadata: dict[str, Any] | None = None) -> Iterator[Any | None]:
    """LLM이 아닌 단계(수집, 랭킹 등)를 span으로 감싼다.

    입력:
      - name: str — span 이름
      - metadata: dict | None
    출력: yield observation 또는 None
    결과: Langfuse 비활성 시 no-op
    """
    client = _get_client()
    if client is None:
        yield None
        return
    try:
        with client.start_as_current_span(name=name, metadata=metadata or {}) as obs:
            yield obs
    except Exception as exc:  # noqa: BLE001
        logger.debug("Langfuse span 실패 %s: %s", name, exc)
        yield None


__all__ = ["llm_span", "trace_span", "tracing_enabled"]
