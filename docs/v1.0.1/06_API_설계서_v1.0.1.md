# SkillRadar API 설계서 v1.0.1

| 항목 | 기준 |
|---|---|
| 작성일 | 2026-11-18 (Asia/Seoul) |
| 문서 버전 | v1.0.1 |
| 구현 기준 | `src/backend/routes.py` 현재 소스 |
| 데이터 형식 | JSON / UTF-8 |
| 인증 | `/api/admin/refresh`만 Bearer 토큰, 나머지 공개 |
| 문서 | `APP_ENV=debug`일 때 `/docs` (Swagger) 노출 |

## 1. 공통 사항

- Base URL: 로컬 `http://localhost:8000`, 배포 시 `https://skill-radar-liart.vercel.app`
- 날짜 파라미터: `YYYY-MM-DD` (Asia/Seoul 기준 수집일)
- 에러 응답: FastAPI 기본 `{"detail": "..."}` 형식
- `platform` 허용값: `claude` | `chatgpt` | `gemini` (`/api/topic-repos`는 `all` 추가 허용)
- `lang` 허용값: `ko` | `en` | `zh`
- 주제 관련 API는 최근 30일(`TOPIC_WINDOW_DAYS`) 수집분만 집계 (`TOPIC_MAX_RESULTS=50`)

## 2. 엔드포인트 목록

| Method | Path | 설명 | 인증 |
|---|---|---|---|
| GET | `/` | 카드 UI + 주제 탐색 (HTML, `Cache-Control: no-cache`) | - |
| GET | `/manifest.json` | PWA 매니페스트 | - |
| GET | `/sw.js` | Service Worker (Web Push 수신) | - |
| GET | `/api/trending` | 플랫폼별 일일 랭킹 | - |
| GET | `/api/dates` | 플랫폼별 수집일 목록 (최신 30개) | - |
| GET | `/api/topics` | 주제 관심순 목록 | - |
| GET | `/api/topic-repos` | 토픽별 저장소 랭킹 | - |
| GET | `/api/related-topics` | 토픽 공기반 관련 주제 | - |
| POST | `/api/admin/refresh` | 수동 전체 수집 실행 | Bearer ADMIN_TOKEN |
| POST | `/api/push/subscribe` | Web Push 구독 등록 | - |
| POST | `/api/push/unsubscribe` | Web Push 구독 해지 | - |
| GET | `/api/push/vapid-key` | VAPID 공개키 조회 | - |
| GET | `/docs` 등 | Swagger (debug 전용) | - |

## 3. API 상세

### 3.1 GET /api/trending

랭킹 조회. 요청 날짜 스냅샷이 없으면 해당 플랫폼 최신 스냅샷으로 폴백한다.

**Query Parameters**

| 이름 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| platform | string | N | `claude` | `claude\|chatgpt\|gemini` |
| date | string | N | 오늘(KST) | `YYYY-MM-DD` 수집일 |
| lang | string | N | `ko` | `ko\|en\|zh` 요약 언어 |

**응답 200**

```json
{
  "platform": "claude",
  "date": "2026-11-18",
  "items": [
    {
      "rank": 1,
      "repo_full_name": "affaan-m/ECC",
      "repo_url": "https://github.com/affaan-m/ECC",
      "description": "The agent harness performance optimization system...",
      "stars": 305500,
      "stars_today": null,
      "language": "JavaScript",
      "license": "MIT",
      "topics": ["ai-agents", "anthropic", "claude"],
      "summary": ["en1", "en2", "en3"],
      "platform": "claude",
      "taxonomy": "agents",
      "rank_score": 187.42,
      "summary_status": "ok"
    }
  ]
}
```

| 필드 | 설명 |
|---|---|
| `stars_today` | 직전 스냅샷 대비 증가 star. 비교 데이터 없으면 `null` |
| `license` | GitHub SPDX id (없으면 `null`) |
| `taxonomy` | 분류 라벨 `agents\|mcp\|skills\|plugins\|devtools\|automation\|data\|other` (LLM 미사용 시 `other`) |
| `rank_score` | `log10(stars+1)*20 + (summary ok?5:0) + confidence*5` |
| `summary_status` | `ok` / `unverified`(검증 재시도 초과) / `failed`(폴백) |
| `summary` | `lang`에 해당하는 3줄 요약. DB에 없으면 description 1줄 폴백 |

**에러**: `400` — platform/lang/date 형식 오류. 데이터 없으면 `items: []` (200).

### 3.2 GET /api/dates

**Query**: `platform` (기본 `claude`)

**응답 200**

```json
{"dates": ["2026-11-18", "2026-11-17"]}
```

최신 30개 수집일, 내림차순.

### 3.3 GET /api/topics (v1.0.1)

최근 30일 수집분에서 등장 횟수가 많은 GitHub 토픽을 관심순으로 반환.

**응답 200**

```json
{"topics": [{"topic": "ai-agents", "count": 12}, {"topic": "mcp", "count": 9}]}
```

최대 50개(`TOPIC_MAX_RESULTS`), `most_common` 순.

### 3.4 GET /api/topic-repos (v1.0.1)

특정 토픽을 가진 저장소를 반환. 정렬은 `rank_score`(없으면 최하위) → `stars` 내림차순.
같은 repo가 여러 스냅샷에 있으면 star가 가장 높은 항목 1개만 채택한다.

**Query Parameters**

| 이름 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| topic | string | Y | - | GitHub topic 이름 (최대 100자) |
| platform | string | N | `all` | `all\|claude\|chatgpt\|gemini` |
| lang | string | N | `ko` | `ko\|en\|zh` |
| limit | int | N | `10` | 1~50으로 클램프 |

**응답 200**: `TrendingResponse`와 동일 형태 (`platform`은 요청값, `date`는 오늘). 각 item의 `rank`는 원본 스냅샷의 rank 값이며, 프론트는 표시 순서로 1부터 다시 매긴다.

**에러**: `400` — topic 누락/초과, platform/lang 오류.

### 3.5 GET /api/related-topics (v1.0.1)

특정 토픽과 함께 등장한 다른 토픽을 공기반 횟수 순으로 반환.

**Query**: `topic` (필수, 최대 100자)

**응답 200**

```json
{"topic": "mcp", "related": [{"topic": "ai-agents", "score": 7}, {"topic": "claude", "score": 5}]}
```

최대 10개(`most_common(10)`).

### 3.6 POST /api/admin/refresh

전체 플랫폼 수집 + Top1 푸시를 즉시 실행한다.

**Headers**: `Authorization: Bearer <ADMIN_TOKEN>`

**응답**

- `200` `{"status": "ok"}` — 실행 완료(플랫폼별 실패는 내부 격리)
- `401` — 토큰 미설정 또는 불일치 (`ADMIN_TOKEN` 미설정 시 항상 401)

### 3.7 POST /api/push/subscribe

```json
{"endpoint": "https://fcm.googleapis.com/...", "keys": {"p256dh": "...", "auth": "..."}}
```

같은 endpoint는 upsert. 응답 `{"status": "ok"}`. endpoint는 10~1000자 검증.

### 3.8 POST /api/push/unsubscribe

동일 바디. endpoint 삭제 후 `{"status": "ok"}`.

### 3.9 GET /api/push/vapid-key

```json
{"key": "<VAPID 공개키 또는 빈 문자열>"}
```

푸시 미설정(`VAPID_*` 미입력) 시 `key: ""` → 프론트는 구독 버튼 비활성화.

### 3.10 GET /manifest.json, GET /sw.js, GET /

- `/manifest.json`: `static/manifest.json`을 `application/manifest+json`으로 서빙 (PWA)
- `/sw.js`: `static/sw.js` 서비스 워커 — push 이벤트에서 `showNotification`
- `/`: Jinja2 `index.html` 렌더링, `Cache-Control: no-cache` 헤더

## 4. 호출 예시

```bash
# 오늘 Claude 랭킹 (한글)
curl "http://localhost:8000/api/trending?platform=claude&lang=ko"

# 특정 날짜 ChatGPT 랭킹 (EN)
curl "http://localhost:8000/api/trending?platform=chatgpt&date=2026-11-18&lang=en"

# 주제 관심순 / 주제별 저장소 / 관련 주제
curl "http://localhost:8000/api/topics"
curl "http://localhost:8000/api/topic-repos?topic=ai-agents&platform=all&limit=10"
curl "http://localhost:8000/api/related-topics?topic=mcp"

# 수동 수집
curl -X POST http://localhost:8000/api/admin/refresh \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

## 버전 이력

- **v1.0.0** (2026-11-18): 초기 API 명세. trending/dates/push/admin만 존재.
- **v1.0.1** (2026-11-18): `/api/topics`, `/api/topic-repos`, `/api/related-topics`, `/manifest.json`, `/sw.js` 추가. `TrendingItem`에 license/taxonomy/rank_score/summary_status/platform 필드 반영.
