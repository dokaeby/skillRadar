# SkillRadar API 설계서 v1.0.0

| 항목 | 기준 |
|---|---|
| 작성일 | 2026-11-18 (Asia/Seoul) |
| 구현 기준 | `src/backend/routes.py` 현재 소스 |
| 데이터 형식 | JSON / UTF-8 |
| 인증 | `/api/admin/refresh`만 Bearer 토큰, 나머지 공개 |
| 문서 | `APP_ENV=debug`일 때 `/docs` (Swagger) 노출 |

## 1. 공통 사항

- Base URL: 로컬 `http://localhost:8000`, 배포 시 서비스 도메인
- 날짜 파라미터: `YYYY-MM-DD` (Asia/Seoul 기준 수집일)
- 에러 응답: FastAPI 기본 `{"detail": "..."}` 형식
- `platform` 허용값: `claude` | `chatgpt` | `gemini`
- `lang` 허용값: `ko` | `en` | `zh`

## 2. 엔드포인트 목록

| Method | Path | 설명 | 인증 |
|---|---|---|---|
| GET | `/` | 카드 UI (HTML) | - |
| GET | `/api/trending` | 플랫폼별 일일 랭킹 | - |
| GET | `/api/dates` | 플랫폼별 수집일 목록 | - |
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
      "topics": ["ai-agents", "anthropic", "claude"],
      "summary": ["en1", "en2", "en3"]
    }
  ]
}
```

| 필드 | 설명 |
|---|---|
| `stars_today` | 직전 스냅샷 대비 증가 star. 비교 데이터 없으면 `null` |
| `summary` | `lang`에 해당하는 3줄 요약. DB에 없으면 description 1줄 폴백 |

**에러**: `400` — platform/lang/date 형식 오류. 데이터 없으면 `items: []` (200).

### 3.2 GET /api/dates

**Query**: `platform` (기본 `claude`)

**응답 200**

```json
{"dates": ["2026-11-18", "2026-11-17"]}
```

최신 30개 수집일, 내림차순.

### 3.3 POST /api/admin/refresh

전체 플랫폼 수집 + Top1 푸시를 즉시 실행한다.

**Headers**: `Authorization: Bearer <ADMIN_TOKEN>`

**응답**

- `200` `{"status": "ok"}` — 실행 완료(플랫폼별 실패는 내부 격리)
- `401` — 토큰 미설정 또는 불일치 (`ADMIN_TOKEN` 미설정 시 항상 401)

### 3.4 POST /api/push/subscribe

```json
{"endpoint": "https://fcm.googleapis.com/...", "keys": {"p256dh": "...", "auth": "..."}}
```

같은 endpoint는 upsert. 응답 `{"status": "ok"}`.

### 3.5 POST /api/push/unsubscribe

동일 바디. endpoint 삭제 후 `{"status": "ok"}`.

### 3.6 GET /api/push/vapid-key

```json
{"key": "<VAPID 공개키 또는 빈 문자열>"}
```

푸시 미설정(`VAPID_*` 미입력) 시 `key: ""` → 프론트는 구독 버튼 비활성화.

## 4. 호출 예시

```bash
# 오늘 Claude 랭킹 (한글)
curl "http://localhost:8000/api/trending?platform=claude&lang=ko"

# 특정 날짜 ChatGPT 랭킹 (EN)
curl "http://localhost:8000/api/trending?platform=chatgpt&date=2026-11-18&lang=en"

# 수동 수집
curl -X POST http://localhost:8000/api/admin/refresh \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```
