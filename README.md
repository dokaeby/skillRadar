# SkillRadar

Claude / ChatGPT / Gemini용 skill·plugin 저장소를 GitHub에서 매일 자동 수집하고,
LLM이 생성한 3줄 요약(한글·EN·中文)을 카드 UI로 보여주는 웹앱입니다.

## 기능

- **수집**: GitHub Search API로 플랫폼별 Top 10 (`sort=stars&order=desc`, `archived/fork` 제외)
  - 쿼리는 `src/backend/queries.yaml`에서 수정 가능
  - APScheduler가 매일 KST 06:00 자동 실행
  - "오늘 증가 star"는 직전 스냅샷과의 차이로 계산
- **요약**: OpenAI-호환 LLM이 description+README(최대 3000자)로부터
  `summary_en` / `summary_zh` / `summary_ko` 각 3줄 JSON 생성.
  `content_hash` 캐시로 동일 입력 재요약 방지, JSON 파싱 실패 시 1회 재시도,
  최종 실패 시 description 폴백. 항목별 예외 격리.
- **화면**: 플랫폼 탭 3개, 언어 토글(한글/EN/中文), 날짜 선택, 반응형 카드 그리드,
  다크모드, Web Push 알림 구독
  - 프론트엔드 소스는 `frontend/src/*.ts` (TypeScript) → `npm run build`로
    `src/backend/static/*.js`에 컴파일. 프레임워크 없이 바닐라 TS + Tailwind CDN
- **API**:
  - `GET /api/trending?platform=claude|chatgpt|gemini&date=YYYY-MM-DD&lang=ko|en|zh`
  - `GET /api/dates?platform=...`
  - `POST /api/admin/refresh` (Bearer `ADMIN_TOKEN`)
  - `POST /api/push/subscribe`, `POST /api/push/unsubscribe`, `GET /api/push/vapid-key`

## 로컬 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install && npm run build   # frontend TS → src/backend/static/*.js 컴파일
cp .env.example .env   # GITHUB_TOKEN, LLM_API_KEY, ADMIN_TOKEN 설정
uvicorn backend.main:create_app --factory --host 0.0.0.0 --port 8000
```

브라우저에서 http://localhost:8000 접속.

수동 수집:

```bash
curl -X POST http://localhost:8000/api/admin/refresh \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

테스트:

```bash
pytest -q
```

## 환경변수

| 변수 | 설명 |
|---|---|
| `GITHUB_TOKEN` | GitHub PAT (검색 rate limit 30req/min → 분당 제한 준수) |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | OpenAI-호환 채팅 API (기본 gpt-4o-mini) |
| `ADMIN_TOKEN` | `/api/admin/refresh` Bearer 인증 |
| `DATABASE_URL` | `sqlite:///./skillradar.db` (기본) 또는 `postgresql://...` |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_SUBJECT` | Web Push (미설정 시 푸시 비활성) |
| `SCHEDULE_HOUR` / `SCHEDULE_TIMEZONE` | 수집 시각 (기본 6 / Asia/Seoul) |

VAPID 키 생성:

```bash
python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print(v.public_key_urlsafe(), v.private_key_urlsafe())"
```

## 모바일 알림 받기 (Web Push)

서버에서 VAPID 키를 설정하고 `https`로 접속하면 헤더의 **🔔 알림 받기** 버튼으로 구독할 수 있습니다.
아이폰·안드로이드 모두 브라우저 Web Push를 사용하며, 앱 설치는 필요 없습니다.

- **안드로이드**: Chrome에서 사이트 접속 → 🔔 알림 받기 → 권한 허용.
  Chrome이 꺼져 있어도 FCM 경유로 알림이 도착합니다.
- **아이폰 (iOS 16.4+)**: Safari의 웹 푸시는 **홈 화면에 추가된 PWA에서만** 동작합니다.
  1. Safari로 사이트 접속 → 공유 버튼 → **홈 화면에 추가**
  2. 홈 화면의 SkillRadar 아이콘으로 실행 → 🔔 알림 받기 → 권한 허용
- 매일 수집 완료 후 각 플랫폼 Top 1이 푸시로 발송됩니다 (`src/backend/push.py`).
  푸시 발송은 VAPID 키 3종이 모두 설정된 경우에만 활성화됩니다.

## Render 배포

1. GitHub repo 연결 → New → Web Service
2. `render.yaml` Blueprint 사용 시 envVars 자동 생성 (`sync: false` 항목은 Dashboard에서 값 입력)
3. **무료 플랜 주의**: 재시작 시 ephemeral 디스크가 초기화되므로 SQLite 데이터가 날아갑니다.
   영구 저장이 필요하면 Render Postgres를 만들고 `DATABASE_URL`을 `postgresql://...`로 지정하세요
   (코드는 `postgresql+psycopg` 드라이버로 자동 전환됩니다).
4. `uvicorn`은 반드시 `--host 0.0.0.0 --port $PORT`로 바인딩됩니다 (Procfile/`startCommand` 참조).

스케줄러는 웹 서비스 내부 APScheduler로 동작하므로 별도 Cron Job이 필요 없습니다.
단, 무료 플랜 spin-down 상태에서는 스케줄이 실행되지 않을 수 있으니,
정확한 매일 실행이 필요하면 Render Cron Job으로
`python -m backend.cli_collect` 같은 일회성 명령을 등록하는 것을 권장합니다.
