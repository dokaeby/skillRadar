"""큐레이터 상태. schemas.CuratorState에 파이프라인 확장 필드를 추가한다."""

from backend.schemas import CuratorState as _SchemasState
from backend.schemas import RelatedTopic


class CuratorState(_SchemasState):
    """LangGraph 상태. related_topics/stars_today는 schemas에 없어 여기서 확장."""

    related_topics: dict[str, list[RelatedTopic]] = {}
    stars_today: dict[str, int | None] = {}


__all__ = ["CuratorState"]
