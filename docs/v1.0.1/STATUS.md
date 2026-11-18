# Skill Radar — AGENTS.md 대비 구현 현황 (v1.0.1)

> 기준 문서: `AGENTS.md` (구 `desc.md`, DB 자격증명 라인 제거 후 등록)
> 작성일: 2026-11-18

## 구현됨

| 지침 항목 | 구현 위치 | 비고 |
|---|---|---|
| GitHub 수집 (토픽/쿼리 검색) | `src/backend/github_client.py`, `config.py` `platform_queries()` | 플랫폼별 쿼리 YAML/설정 기반 |
| archived/fork 제외 + 사유 기록 | `collector.py` `dedupe_filter` 단계 | 제외 건수를 로그로 기록 (v1.0.1 추가) |
| 중복 제거 (동일 repo 최고 star 유지) | `collector.py` `merged` dict | URL canonical = `full_name` |
| README 수집 (앞 3000자) | `github_client.py` `fetch_readme` | JSON base64 폴백 포함 |
| 프롬프트 인젝션 sanitize | `summarizer.py` `sanitize_readme` | 의심 문구 라인 제거 + 길이 제한 (v1.0.1 추가) |
| LLM 구조화 출력 Pydantic 검증 | `summarizer.py` `LLMSummary` | 3언어 × 3줄 스키마 강제 (v1.0.1 추가) |
| 요약 재시도(최대 3회) + description 폴백 | `summarizer.py` | 파싱 실패/호출 실패 모두 폴백 |
| 요약 캐시 (content_hash) | `collector.py` `_find_cached_summary` | 동일 repo+콘텐츠 재요약 방지 |
| stars_today 증감 | `collector.py` `_previous_stars` | 직전 스냅샷 대비 |
| 한국어 요약 | `summarizer.py` + `translate_lines_ko` | LLM ko 우선, 한글 없으면 Google 번역 |
| Supabase Postgres 저장 | `db.py`, `models.py` | SQLAlchemy 2.x ORM |
| FastAPI 제공 + 반응형 UI | `routes.py`, `frontend/` | PWA/Web Push 포함 |
| 주제 추천 (관심순 + 주제별 Top10) | `/api/topics`, `/api/topic-repos` | v1.0.1 신규 |
| 비밀값 환경변수 관리 | `config.py` (pydantic-settings), `.env` gitignore | 코드/로그 미노출 |
| GitHub rate limit 대응 | `github_client.py` 지수 backoff + Retry-After | 403/429/5xx 재시도 |

## 미구현 — 스택 변경 승인 필요 (AGENTS.md §2 "변경 시 승인 필요")

| 항목 | 상태 | 비고 |
|---|---|---|
| LangChain 1.x | 미도입 | 현재 httpx 직접 호출. 도입 시 모델 팩토리/구조화 출력/도구 계층 재작성 필요 |
| LangGraph 워크플로 | 미도입 | 현재 `collector.py` 선형 파이프라인. 노드 분리·조건 분기·interrupt는 그래프 도입 후 가능 |
| LangSmith 트레이싱/평가 | 미도입 | 평가 지표 체계(§5) 전체가 이에 의존 |
| Redis 캐시 | 미도입 | 현재 인메모리+DB 캐시만 사용 |
| Tavily 관련 주제 확장 | 미도입 | 현재 topics는 GitHub 데이터 내에서만 집계 |
| Ollama 임베딩 의미 검색 | 미도입 | |

## 미구현 — 현재 스택 내 보강 가능 (마일스톤 후보)

| 항목 | 내용 |
|---|---|
| classify taxonomy | 정해진 라벨 분류 + 신뢰도 (현재는 LLM 요약만) |
| verify 노드 | 요약 충실도 검증 (현재 스키마 검증만) |
| rank 고도화 | stars 외 최근 커밋/라이선스/신뢰 신호 반영 |
| related 주제 추천 | repo 단위 인접/보완/대안 주제 |
| publish 사람 승인 | 다이제스트 공개 전 interrupt (그래프 도입 시) |
| ETag/조건부 요청 | GitHub Search API는 ETag 미지원 — Contents API에만 부분 적용 가능 |
| 골든 데이터셋/평가 | LangSmith 없이도 pytest 기반 회귀 테스트로 시작 가능 |
| Docker 이미지 | 현재 Vercel 서버리스 배포, Render 설정만 존재 |
| pyright strict | ruff만 설정됨 |

## 다음 권장 순서

1. AGENTS.md §0 전제 항목 확정 (사용자/배포 형태) — 현재 "공개 서비스 + Vercel"로 간주
2. LangChain/LangGraph/LangSmith 도입 여부 승인 → 승인 시 M2~M3 마일스톤 진행
3. 미승인 상태에서는 classify/verify/rank 보강부터 진행 가능

## 알려진 이슈

- Vercel 서버리스에서는 APScheduler가 동작하지 않으므로 수집은 Vercel Cron(`/api/admin/refresh`)에 의존
- Supabase는 세션 모드 pooler(5432) 사용 — 트랜잭션 모드(6543)는 prepared statement 미지원으로 사용 불가
- iOS Web Push는 홈 화면 추가 PWA에서만 동작 (iOS 16.4+)
- `desc.md` 원본 상단에 DB 비밀번호가 평문으로 포함되어 있었음 — AGENTS.md 등록 시 해당 라인 제거, 비밀번호는 Supabase에서 재설정 권장
</file_path>
/Users/sec/Documents/python-projects/skillRadar/docs/v1.0.1/STATUS.md