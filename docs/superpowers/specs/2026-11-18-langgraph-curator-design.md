# SkillRadar LangGraph 큐레이터 전환 설계 (v1.0.1)

## 의도와 이유
AGENTS.md §4 워크플로를 현재 선형 `collector.py` 파이프라인에서 LangGraph
StateGraph로 옮긴다. 목적은 포트폴리오 관점의 "에이전트 품질 측정" —
노드별 재시도, verify 게이트, LangSmith 트레이스, 골든 데이터셋 평가.

## 목표 / 비목표
- 목표: classify → summarize → verify(재시도≤2) → rank → related 노드,
  LangSmith 연동(키 없으면 no-op), Redis 캐시(Upstash, 미설정 시 폴백),
  골든 데이터셋 평가 스크립트, pyright strict(신규 모듈 한정).
- 비목표: Tavily 도입(비용), 사람 승인 interrupt publish(후속),
  프론트엔드 대개편, 마이크로서비스 분리.

## 결정 사항 (사용자 확인 완료)
- LangSmith: API 키 없음 → `LANGSMITH_TRACING`/`LANGSMITH_API_KEY` env가
  있을 때만 활성화, 없으면 완전 no-op.
- Redis: Upstash 무료 티어. `REDIS_URL` env. 미설정/연결 실패 시
  인메모리/무시 폴백 (프로덕션 중단 없음).
- 모델: classify/verify/judge = `gemini-3.5-flash-lite`
  (`LLM_MODEL` env로 변경 가능). judge는 생성과 동일 모델이지만
  별도 프롬프트·별도 호출로 분리(AGENTS.md "자기 채점 금지"는
  역할 분리로 충족, 모델 분리는 env `LLM_JUDGE_MODEL`로 확장 가능).

## 구조
```
src/backend/
  schemas.py      # RepoRaw, RepoClean, Classification, VerifiedSummary,
                  # RankedRepo, RelatedTopic, CuratorState (Pydantic)
  graph/
    state.py      # CuratorState (Pydantic)
    nodes.py      # collect/dedupe_filter/sanitize/classify/summarize/
                  # verify/rank/related/publish 노드 함수
    pipeline.py   # StateGraph 빌드 + 실행 엔트리
  llm_tasks.py    # classify_repo, verify_summary, judge_summary
                  # (기존 Summarizer 재사용, 구조화 출력)
  storage/
    cache.py      # Redis 래퍼 (get/set JSON, TTL, 폴백)
  eval/
    dataset.json  # 골든 데이터셋 (repo → 기대 classification)
    run_eval.py   # 분류 정확도/스키마 통과율 측정 CLI
    metrics.py    # precision/recall 계산
tests/
  test_graph.py, test_llm_tasks.py, test_eval.py
```

## 데이터 흐름
1. collect: 기존 GitHubClient 검색 → RepoHit 목록 (Redis 캐시 TTL 20h)
2. dedupe_filter: archived/fork/중복 제거 + 제외 사유 집계 (기존 로직 이관)
3. sanitize: sanitize_readme (기존) + 불필요 마크업 제거
4. classify: taxonomy 8개 중 라벨+신뢰도 (LLM 구조화 출력)
   taxonomy = agents|mcp|skills|plugins|devtools|automation|data|other
5. summarize: 기존 Summarizer 3개 언어 요약 (content_hash 캐시 유지)
6. verify: 요약 각 언어가 README 근거에 있는지 LLM 검증.
   실패 시 summarize 재호출 최대 2회, 초과 시 summary_status="unverified"
   로 표시하고 폴백 유지 (수집 중단 없음)
7. rank: rank_score = log10(stars)*20 + stars_today 보너스(최대15)
   + 라이선스 확인(+5) + 검증 통과(+5). DB 컬럼 `rank_score`에 저장.
8. related: 같은 플랫폼 스냅샷 내 토픽 공기반(topics 교집합)으로
   관련 주제 계산 — LLM 호출 없음, `/api/related-topics`로 노출
9. publish: 기존 Snapshot/SnapshotItem 저장 (graph 결과 → ORM 변환)

## DB 변경 (Supabase 마이그레이션)
`snapshot_items`에 컬럼 추가:
- `taxonomy` VARCHAR(50) NULL
- `taxonomy_confidence` FLOAT NULL
- `rank_score` FLOAT NULL
- `summary_status` VARCHAR(20) NOT NULL DEFAULT 'ok'  -- ok|unverified|failed

## LangSmith
`LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` 설정 시에만
langsmith trace 컨텍스트로 graph 실행을 감싼다. 미설정 시 순수 로컬 실행.

## Redis
`REDIS_URL` 설정 시 `redis.asyncio`로 검색 결과 캐시.
미설정/오류 시 NullCache(항상 miss)로 동작 — 수집은 정상 진행.

## 평가
`python -m backend.eval.run_eval` — 골든 데이터셋 N개 repo에 대해
classify 정확도(정답 라벨 대비), verify 스키마 통과율, 지연을 출력.
결과는 `docs/experiments/YYYY-MM-DD-*.md`에 기록.
CI 게이트는 기준선 측정 후 결정(AGENTS.md §5) — 이번엔 측정만.

## pyright
`pyrightconfig.json`: 전체 `standard`, `src/backend/graph`,
`src/backend/eval`, `src/backend/llm_tasks.py`, `src/backend/schemas.py`는
`strict`. 기존 코드베이스는 strict 전환 비용이 커 표준 모드 유지.

## 검증
- pytest 전체 통과 (기존 23 + 신규 graph/llm_tasks/eval 테스트)
- Supabase 마이그레이션 적용 후 `/api/trending`에 신규 필드 확인
- `/api/related-topics?topic=` 200 응답
- LangSmith/Redis 미설정 상태에서 수집·API 정상 (폴백 검증)
