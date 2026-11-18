"""큐레이터 파이프라인 Pydantic 스키마 (AGENTS.md §6 핵심 모델)."""

from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from backend.github_client import RepoHit

from pydantic import BaseModel, Field

Taxonomy = Literal[
    "agents", "mcp", "skills", "plugins", "devtools", "automation", "data", "other"
]


class GitHubLike(Protocol):
    """GitHubClient와 테스트 fake가 만족하는 최소 인터페이스."""

    async def search_repositories(self, query: str, per_page: int = 30) -> list["RepoHit"]: ...
    async def fetch_readme(self, full_name: str) -> str: ...
    async def aclose(self) -> None: ...


class SummarizerLike(Protocol):
    """Summarizer와 테스트 fake가 만족하는 최소 인터페이스."""

    async def summarize(
        self, platform: str, full_name: str, description: str | None, readme: str
    ) -> dict[str, list[str]]: ...
    async def aclose(self) -> None: ...


class RepoRaw(BaseModel):
    """GitHub 검색 결과 원본."""

    full_name: str
    html_url: str
    description: str | None = None
    stars: int = 0
    language: str | None = None
    topics: list[str] = Field(default_factory=list)
    archived: bool = False
    fork: bool = False
    license: str | None = None


class RepoClean(BaseModel):
    """필터·정제·README 수집이 끝난 저장소."""

    repo: RepoRaw
    readme: str = ""
    sanitized_readme: str = ""


class Classification(BaseModel):
    """taxonomy 분류 결과."""

    label: Taxonomy = "other"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SummaryResult(BaseModel):
    """3개 언어 3줄 요약 + 검증 상태."""

    en: list[str] = Field(default_factory=list)
    zh: list[str] = Field(default_factory=list)
    ko: list[str] = Field(default_factory=list)
    status: Literal["ok", "unverified", "failed"] = "ok"


class RankedRepo(BaseModel):
    """랭킹 점수가 계산된 최종 항목."""

    clean: RepoClean
    classification: Classification
    summary: SummaryResult
    rank_score: float = 0.0


class RelatedTopic(BaseModel):
    """관련 주제 (토픽 공기반)."""

    topic: str
    score: float = 0.0


class CuratorState(BaseModel):
    """LangGraph 상태. 각 노드가 갱신한다."""

    platform: str = "claude"
    queries: list[str] = Field(default_factory=list)
    repos_raw: list[RepoRaw] = Field(default_factory=list)
    repos_clean: list[RepoClean] = Field(default_factory=list)
    classifications: dict[str, Classification] = Field(default_factory=dict)
    summaries: dict[str, SummaryResult] = Field(default_factory=dict)
    ranked: list[RankedRepo] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    retries: dict[str, int] = Field(default_factory=dict)
