# Pyright 설정 메모 (2026-11-18)

## 결정

`pyrightconfig.json`은 프로젝트 전체에 `typeCheckingMode: "standard"`를 적용한다.
pyrightconfig.json은 파일별 typeCheckingMode 오버라이드를 지원하지 않으므로,
설계 문서(`docs/superpowers/specs/2026-11-18-langgraph-curator-design.md`)의
"신규 모듈 strict" 목표는 설정이 아니라 코드 스타일로 충족한다.

## strict-호환 스타일로 작성된 신규 모듈

- `src/backend/schemas.py` — 모든 필드 타입 명시, Literal 제약
- `src/backend/llm_tasks.py` — 키워드 전용 인자, `httpx.AsyncClient | None`, 반환 타입 명시
- `src/backend/graph/` — 노드 함수·상태 타입 명시
- `src/backend/storage/cache.py` — `JsonCache`/`NullCache`/`RedisJsonCache` 타입 명시
- `src/backend/eval/` — `metrics.py` 순수 함수, `run_eval.py` 반환 타입 명시

## 승격 방법 (후속 작업)

strict 전환이 필요해지면 두 가지 방법이 있다:

1. **파일 단위 strict**: pyright CLI의 `--verifytypes`는 타입 stub 검증용이라
   용도가 다르다. 대신 `basedpyright`(pyright 포크)는 `typeCheckingMode`의
   per-file 오버라이드를 지원하지 않으므로, 파일 단위 strict는
   `# pyright: strict` 파일 상단 주석으로 가능하다 (pyright/basedpyright 공통 지원).
   신규 모듈 상단에 `# pyright: strict`를 추가하면 된다.
2. **전체 strict**: 기존 코드베이스(collector, routes 등)의 strict 전환 비용이
   크므로 별도 작업으로 진행한다.
