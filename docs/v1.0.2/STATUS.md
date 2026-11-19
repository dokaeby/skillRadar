# Skill Radar — AGENTS.md 대비 구현 현황 (v1.0.2)

> 기준 문서: `AGENTS.md` (구 `desc.md`, DB 자격증명 라인 제거 후 등록)
> 작성일: 2026-11-19 (v1.0.1: 2026-11-18)

## v1.0.2 변경 요약

- **Redis 제거**: `storage/cache.py`, `redis` 의존성, `REDIS_URL`/`redis_enabled` 설정, `tests/test_cache.py` 삭제. 요약 캐시는 `content_hash` 기반 DB 조회(`collector._find_cached_summary`)만 사용.
- **Gmail 발송 기능 없음**: 저장소 전체에 Gmail/SMTP/이메일 발송 구현이 존재하지 않음. 알림은 Web Push(VAPID)만 사용.
- **Vercel Cron 수정**: `/api/admin/refresh`가 GET·POST 모두 허용, `CRON_SECRET`(=`ADMIN_TOKEN`) Bearer 인증. 기존 POST 전용이라 cron이 405로 실패하던 문제 해소. `VERCEL` env에서는 APScheduler 비활성화.
- **프론트엔드 경로 이동**: `frontend/src/*.ts` → `src/frontend/*.ts` (`tsconfig*.json` 갱신).
- **함수 주석**: 전 모듈 함수에 입력/출력/결과 독스트링(JSDoc) 추가.
- **운영 버그 수정**: Supabase pooler `DuplicatePreparedStatement`(psycopg prepared statement 비활성화), 플랫폼 동시 수집 시 런타임 의존성 race 분리.
- **리팩토링**: 미사용 `judge_summary`·`build_pipeline`·`translate_fallback` 플래그·`stars_today` 상태필드 제거, `langchain`/`python-dotenv` 미사용 의존성 제거, nodes 상태 접근을 `CuratorState` 타입으로 정리, routes 검증/타입 보강.
- **수집 실패 알림 + 중복 수집 방지**: 전 플랫폼 수집 실패 시 Web Push 알림, 같은 날짜 스냅샷 존재 시 스킵(`?force=true`로 재수집).
- **content_hash 캐시 확장**: `SummaryCacheFn`→`RepoCacheFn`으로 분류·요약·검증 3개 노드가 동일 해시의 이전 레코드를 재사용. verify는 `status!='ok'` 요약과 이미 검증 통과한 캐시 히트를 스킵해 LLM 호출 절감.

## 구현됨

| 지침 항목 | 구현 위치 | 비고 |
|---|---|---|
| GitHub 수집 (토픽/쿼리 검색) | `src/backend/github_client.py`, `config.py` `platform_queries()` | 플랫폼별 쿼리 YAML/설정 기반 |
| archived/fork 제외 + 사유 기록 | `collector.py` `dedupe_filter` 단계 | 제외 건수를 로그로 기록 |
| 중복 제거 (동일 repo 최고 star 유지) | `collector.py` `merged` dict | URL canonical = `full_name` |
| README 수집 (앞 3000자) | `github_client.py` `fetch_readme` | JSON base64 폴백 포함 |
| 프롬프트 인젝션 sanitize | `summarizer.py` `sanitize_readme` | 의심 문구 라인 제거 + 길이 제한 |
| LLM 구조화 출력 Pydantic 검증 | `summarizer.py` `LLMSummary` | 3언어 × 3줄 스키마 강제 |
| 요약 재시도(최대 3회) + description 폴백 | `summarizer.py` | 파싱 실패/호출 실패 모두 폴백 |
| content_hash 캐시 (분류·요약·검증) | `collector.py` `_find_cached_repo` → `RepoCacheFn` | 동일 repo+콘텐츠면 LLM 호출 0회 |
| stars_today 증감 | `collector.py` `_previous_stars` | 직전 스냅샷 대비 |
| 한국어 요약 | `summarizer.py` + `translate_lines_ko` | LLM ko 우선, 한글 없으면 Google 번역 |
| Supabase Postgres 저장 | `db.py`, `models.py` | SQLAlchemy 2.x ORM, psycopg prepared statement 비활성화 |
| FastAPI 제공 + 반응형 UI | `routes.py`, `src/frontend/` | PWA/Web Push 포함 |
| 주제 추천 (관심순 + 주제별 Top10) | `/api/topics`, `/api/topic-repos` | |
| 비밀값 환경변수 관리 | `config.py` (pydantic-settings), `.env` gitignore | 코드/로그 미노출 |
| GitHub rate limit 대응 | `github_client.py` 지수 backoff + Retry-After | 403/429/5xx 재시도 |
| 일일 예약 수집 | Vercel Cron → `GET /api/admin/refresh` (`CRON_SECRET` Bearer) | 매일 06:00 KST(UTC 21:00) 예정, Hobby 플랜 ±59분 오차 가능 |

## 스택 확장 구현 완료

| 항목 | 상태 | 구현 위치 | 비고 |
|---|---|---|---|
| LangGraph 큐레이터 파이프라인 | ✅ | `src/backend/graph/` (state/nodes/pipeline) | collect→dedupe_filter→sanitize→classify→summarize→verify→rank→related. 플랫폼별 런타임 의존성 분리(동시 수집 race 수정) |
| classify taxonomy 분류 | ✅ | `llm_tasks.classify_repo` + `graph/nodes.classify` | 8개 라벨 + confidence, `LLM_JUDGE_MODEL` |
| verify 노드 | ✅ | `llm_tasks.verify_summary` + `graph/nodes.verify` | 실패 시 재요약 최대 2회 → `summary_status='unverified'` |
| rank 고도화 | ✅ | `graph/nodes.rank` | `rank_score` 저장, topic-repos 정렬에 반영 |
| related 주제 | ✅ | `graph/nodes.related` + `GET /api/related-topics` + 사이드바 칩 UI | 토픽 공기반 점수, 최근 30일 수집분 기준 |
| 골든 데이터셋 평가 | ✅ | `src/backend/eval/` (dataset.json 10개, metrics.py, run_eval.py) | `python -m backend.eval.run_eval` → docs/experiments/ 기록 |
| LangSmith | ✅ 준비 완료 | `graph/pipeline.py` env 제어 | `LANGSMITH_API_KEY`+`LANGSMITH_TRACING=true`일 때만 활성 |
| ~~Redis 캐시~~ | ❌ 제거됨 (v1.0.2) | — | 사용처 없어 `storage/cache.py`·의존성·설정 삭제. content_hash 캐시로 대체 |
| LangGraph 체크포인터 | ✅ | `graph/pipeline.py` `_checkpointer` | `CHECKPOINT_PATH` 지정 시 AsyncSqliteSaver, 미설정 시 MemorySaver |
| pyright | ✅ 통과 | `pyrightconfig.json` | `npx pyright` 0 errors |
| 이메일/Gmail 발송 | ❌ 미사용 | — | 구현 없음. 알림 채널은 Web Push(VAPID) 단일 |
| Tavily | ❌ 제외 | — | 비용 발생 — 사용자 지시로 도입하지 않음 |
| Ollama 임베딩 의미 검색 | 미도입 | — | |

## 검증 결과 (2026-11-19, v1.0.2)

- `pytest`: 37 passed (`test_cache.py` Redis 7개 + `judge_summary` 4개 테스트 삭제 반영)
- `npx pyright`: 0 errors
- `ruff check`: All checks passed (0 errors)
- `npm run build` (tsc): 통과 → `src/backend/static/{app,push,sw}.js`
- Vercel Cron end-to-end: `vercel crons run /api/admin/refresh` → GET 인증 통과 → 3개 플랫폼 `2026-11-19` 스냅샷 생성, Web Push 발송 확인(사용자 수신 확인)

## 미구현 — 현재 스택 내 보강 가능 (마일스톤 후보)

| 항목 | 내용 |
|---|---|
| publish 사람 승인 | 다이제스트 공개 전 interrupt (그래프 도입 시) |
| ETag/조건부 요청 | GitHub Search API는 ETag 미지원 — Contents API에만 부분 적용 가능 |
| Docker 이미지 | 현재 Vercel 서버리스 배포, Render 설정만 존재 |
| pyright strict | 파일별 `# pyright: strict` 점진 적용 여지 |
| 수집 시간 단축 | 캐시 미스(신규/변경 repo) 시 여전히 ~222초 — LLM rate limit(~15 RPM)이 병목. 캐시 히트 시 플랫폼당 ~6초 (claude 1개 실측) |

## 다음 권장 순서

1. AGENTS.md §0 전제 항목 확정 (사용자/배포 형태) — 현재 "공개 서비스 + Vercel"로 간주
2. LangSmith API 키 발급 시 트레이싱·평가 실험 활성화
3. 수집 소요 시간 모니터링 — 캐시 미스 시 ~222초로 300초 제한에 근접. 캐시 히트 일수록 ~수십 초로 단축됨을 실측 확인

## 알려진 이슈

- Vercel 서버리스에서는 APScheduler가 동작하지 않으므로 수집은 Vercel Cron(`/api/admin/refresh`, GET)에 의존. `VERCEL` env에서 스케줄러 자동 비활성화
- Vercel Hobby Cron은 예약 시각 ±59분 내 발화 — 매일 06:00~06:59 KST 사이 알림 가능
- Supabase는 세션 모드 pooler(5432) 사용 — 트랜잭션 모드(6543)는 prepared statement 미지원으로 사용 불가 (코드에서 비활성화 처리됨)
- iOS Web Push는 홈 화면 추가 PWA에서만 동작 (iOS 16.4+)
- `desc.md` 원본 상단에 DB 비밀번호가 평문으로 포함되어 있었음 — AGENTS.md 등록 시 해당 라인 제거, 비밀번호는 Supabase에서 재설정 권장
- Gmail 등 이메일 발송 채널은 없음 — 알림은 Web Push 구독 기반만 지원<|end_message|><|message_model|>exec<|content_invoke_tool_json|>{