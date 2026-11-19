"""큐레이터 상태. schemas.CuratorState에 파이프라인 확장 필드를 추가한다."""

from backend.schemas import CuratorState as _SchemasState
from backend.schemas import RelatedTopic


class CuratorState(_SchemasState):
    """LangGraph 상태. related_topics는 schemas에 없어 여기서 확장한다.

    입력: 파이프라인 초기 입력 {"platform", "queries"} 및 노드별 갱신 dict
    출력: 각 노드가 갱신하는 누적 상태 (repos_raw→ranked→related_topics)
    결과: ainvoke 완료 시 최종 CuratorState 반환
    """

    related_topics: dict[str, list[RelatedTopic]] = {}


__all__ = ["CuratorState"]
