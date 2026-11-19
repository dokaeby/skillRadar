"""LangGraph StateGraph 빌드 및 플랫폼 파이프라인 실행 엔트리."""

import logging
import os
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from backend.config import Settings
from backend.schemas import GitHubLike, SummarizerLike

from . import nodes
from .state import CuratorState

logger = logging.getLogger(__name__)


def _build_graph() -> StateGraph:
    graph = StateGraph(CuratorState)
    graph.add_node("collect", nodes.collect)
    graph.add_node("dedupe_filter", nodes.dedupe_filter)
    graph.add_node("sanitize", nodes.sanitize)
    graph.add_node("classify", nodes.classify)
    graph.add_node("summarize", nodes.summarize)
    graph.add_node("verify", nodes.verify)
    graph.add_node("rank", nodes.rank)
    graph.add_node("related", nodes.related)

    graph.set_entry_point("collect")
    graph.add_edge("collect", "dedupe_filter")
    graph.add_edge("dedupe_filter", "sanitize")
    graph.add_edge("sanitize", "classify")
    graph.add_edge("classify", "summarize")
    graph.add_edge("summarize", "verify")
    graph.add_edge("verify", "rank")
    graph.add_edge("rank", "related")
    graph.add_edge("related", END)
    return graph


def build_pipeline() -> Any:
    """collect → … → related → END 선형 그래프를 컴파일해 반환한다."""
    return _build_graph().compile(checkpointer=MemorySaver())


@asynccontextmanager
async def _checkpointer(settings: Settings) -> AsyncIterator[Any]:
    """checkpoint_path가 있으면 SqliteSaver, 없거나 미설치 시 MemorySaver."""
    if not settings.checkpoint_path:
        yield MemorySaver()
        return
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    except ImportError:
        logger.warning(
            "langgraph-checkpoint-sqlite 미설치 — MemorySaver로 폴백 "
            "(checkpoint_path=%s)",
            settings.checkpoint_path,
        )
        yield MemorySaver()
        return
    async with AsyncSqliteSaver.from_conn_string(settings.checkpoint_path) as saver:
        yield saver


async def run_platform_pipeline(
    platform: str,
    queries: list[str],
    settings: Settings,
    github: GitHubLike | None = None,
    summarizer: SummarizerLike | None = None,
    summary_cache: Any = None,
) -> CuratorState:
    """한 플랫폼의 전체 큐레이션 파이프라인을 실행하고 최종 상태를 반환한다.

    summary_cache: async (full_name, description, sanitized_readme) ->
    SummaryResult|dict|tuple|None. 히트 시 해당 repo의 LLM 요약을 건너뛴다.
    """
    nodes.configure_runtime(
        platform,
        settings=settings, github=github, summarizer=summarizer,
        summary_cache=summary_cache,
    )
    try:
        # LangSmith 트레이싱: 설정 시에만 env를 켜고 실행 후 원복한다.
        env_keys = ("LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGCHAIN_PROJECT")
        saved = {k: os.environ.get(k) for k in env_keys}
        if settings.langsmith_enabled:
            os.environ["LANGSMITH_TRACING"] = "true"
            os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.get_secret_value()
            os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        else:
            os.environ["LANGSMITH_TRACING"] = "false"
        try:
            async with AsyncExitStack() as stack:
                checkpointer = await stack.enter_async_context(_checkpointer(settings))
                compiled = _build_graph().compile(checkpointer=checkpointer)
                result = await compiled.ainvoke(
                    {"platform": platform, "queries": list(queries)},
                    config={"configurable": {"thread_id": f"{platform}-{uuid4().hex}"}},
                )
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        if isinstance(result, CuratorState):
            return result
        return CuratorState.model_validate(result)
    finally:
        nodes.reset_runtime(platform)
