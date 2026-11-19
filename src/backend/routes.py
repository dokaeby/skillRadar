"""API + 서버 렌더링 라우트."""

import hmac
import logging
from collections import Counter
from collections.abc import Sequence
from datetime import date as date_type
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from backend.config import PLATFORMS, Settings, get_settings
from backend.db import get_session
from backend.github_client import today_kst
from backend.models import Snapshot, SnapshotItem
from backend.scheduler import run_daily_collect

logger = logging.getLogger(__name__)
router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent


class TrendingItem(BaseModel):
    rank: int
    repo_full_name: str
    repo_url: str
    description: str | None
    stars: int
    stars_today: int | None
    language: str | None
    license: str | None = None
    topics: list[str]
    summary: list[str]
    platform: str | None = None
    taxonomy: str | None = None
    rank_score: float | None = None
    summary_status: str | None = None


class TrendingResponse(BaseModel):
    platform: str
    date: str
    items: list[TrendingItem]


class SubscribeBody(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    keys: dict[str, str]


def _serialize_item(item: SnapshotItem, lang: str, platform: str | None = None) -> TrendingItem:
    """

    입력:
      - item: SnapshotItem
      - lang: str
      - platform: str | None
    출력: TrendingItem
    결과: 없음 (읽기 전용 직렬화)
    """
    return TrendingItem(
        rank=item.rank,
        repo_full_name=item.repo_full_name,
        repo_url=item.repo_url,
        description=item.description,
        stars=item.stars,
        stars_today=item.stars_today,
        language=item.language,
        license=item.license,
        topics=item.topics or [],
        summary=item.summary_for(lang),
        platform=platform,
        taxonomy=item.taxonomy,
        rank_score=item.rank_score,
        summary_status=item.summary_status,
    )


def _get_snapshot(
    session: Session, platform: str, collected: date_type
) -> Snapshot | None:
    """

    입력:
      - session: Session
      - platform: str
      - collected: date_type
    출력: Snapshot | None — 없으면 None
    결과: 해당 플랫폼+날짜 스냅샷 1건 조회
    """
    return session.execute(
        select(Snapshot)
        .where(Snapshot.platform == platform, Snapshot.collected_date == collected)
    ).scalar_one_or_none()


def _require_lang(lang: str) -> None:
    """lang 파라미터가 ko|en|zh인지 검증한다.

    입력: lang — 쿼리 파라미터
    출력: 없음
    결과: 허용 외 값이면 400 HTTPException
    """
    if lang not in ("ko", "en", "zh"):
        raise HTTPException(status_code=400, detail="lang은 ko|en|zh 중 하나")


@router.get("/api/trending", response_model=TrendingResponse)
async def trending(
    platform: str = "claude",
    date: str | None = None,
    lang: str = "ko",
    session: Session = Depends(get_session),
) -> TrendingResponse:
    """

    입력:
      - platform: str
      - date: str | None
      - lang: str
      - session: Session
    출력: TrendingResponse
    결과: 없음 (DB 읽기)
    """
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail="platform은 claude|chatgpt|gemini 중 하나")
    _require_lang(lang)
    try:
        collected = date_type.fromisoformat(date) if date else date_type.fromisoformat(today_kst())
    except ValueError:
        raise HTTPException(status_code=400, detail="date는 YYYY-MM-DD 형식") from None

    snap = _get_snapshot(session, platform, collected)
    if snap is None:
        # 최신 스냅샷으로 폴백
        snap = session.execute(
            select(Snapshot)
            .where(Snapshot.platform == platform)
            .order_by(Snapshot.collected_date.desc())
            .limit(1)
        ).scalar_one_or_none()
    if snap is None:
        return TrendingResponse(platform=platform, date=collected.isoformat(), items=[])
    return TrendingResponse(
        platform=platform,
        date=snap.collected_date.isoformat(),
        items=[_serialize_item(i, lang, platform=platform) for i in snap.items],
    )


@router.get("/api/dates")
async def available_dates(
    platform: str = "claude",
    session: Session = Depends(get_session),
) -> dict:
    """

    입력:
      - platform: str
      - session: Session
    출력: dict
    결과: 없음 (DB 읽기)
    """
    rows = session.execute(
        select(Snapshot.collected_date)
        .where(Snapshot.platform == platform)
        .order_by(Snapshot.collected_date.desc())
        .limit(30)
    ).scalars().all()
    return {"dates": [d.isoformat() for d in rows]}


TOPIC_WINDOW_DAYS = 30
TOPIC_MAX_RESULTS = 50


def _recent_items(session: Session) -> Sequence[Row[SnapshotItem, str]]:
    """최근 TOPIC_WINDOW_DAYS일 스냅샷의 (item, platform) 행 목록.

    입력:
      - session: Session
    출력: Sequence[Row[SnapshotItem, str]]
    결과: 토픽 통계/추천 쿼리의 입력 행 반환
    """
    since = date_type.today() - timedelta(days=TOPIC_WINDOW_DAYS)
    return session.execute(
        select(SnapshotItem, Snapshot.platform)
        .join(Snapshot, SnapshotItem.snapshot_id == Snapshot.id)
        .where(Snapshot.collected_date >= since)
    ).all()


@router.get("/api/topics")
async def topics(session: Session = Depends(get_session)) -> dict:
    """최근 수집분에서 등장 횟수가 많은 GitHub 토픽을 관심순으로 반환.

    입력:
      - session: Session
    출력: dict
    결과: 없음 (DB 읽기)
    """
    counts: Counter[str] = Counter()
    for item, _platform in _recent_items(session):
        for topic in set(item.topics or []):
            counts[topic] += 1
    return {
        "topics": [
            {"topic": t, "count": c}
            for t, c in counts.most_common(TOPIC_MAX_RESULTS)
        ]
    }


@router.get("/api/topic-repos")
async def topic_repos(
    topic: str,
    platform: str = "all",
    lang: str = "ko",
    limit: int = 10,
    session: Session = Depends(get_session),
) -> TrendingResponse:
    """특정 토픽을 가진 저장소를 스타 순으로 반환 (플랫폼별 필터 가능).

    입력:
      - topic: str
      - platform: str
      - lang: str
      - limit: int
      - session: Session
    출력: TrendingResponse
    결과: 없음 (DB 읽기)
    """
    if not topic or len(topic) > 100:
        raise HTTPException(status_code=400, detail="topic 파라미터가 필요합니다")
    if platform != "all" and platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail="platform은 all|claude|chatgpt|gemini")
    _require_lang(lang)
    limit = max(1, min(limit, 50))

    best: dict[str, tuple[SnapshotItem, str]] = {}
    for item, plat in _recent_items(session):
        if topic not in (item.topics or []):
            continue
        if platform != "all" and plat != platform:
            continue
        prev = best.get(item.repo_full_name)
        if prev is None or item.stars > prev[0].stars:
            best[item.repo_full_name] = (item, plat)

    ranked = sorted(
        best.values(),
        key=lambda pair: (
            pair[0].rank_score if pair[0].rank_score is not None else float("-inf"),
            pair[0].stars,
        ),
        reverse=True,
    )[:limit]
    return TrendingResponse(
        platform=platform,
        date=date_type.today().isoformat(),
        items=[
            _serialize_item(item, lang, platform=plat)
            for item, plat in ranked
        ],
    )


@router.get("/api/related-topics")
async def related_topics(
    topic: str,
    session: Session = Depends(get_session),
) -> dict:
    """특정 토픽과 함께 등장한 다른 토픽을 공기반 점수 순으로 반환.

    입력:
      - topic: str
      - session: Session
    출력: dict
    결과: 없음 (DB 읽기)
    """
    if not topic or len(topic) > 100:
        raise HTTPException(status_code=400, detail="topic 파라미터가 필요합니다")
    co: Counter[str] = Counter()
    for item, _platform in _recent_items(session):
        topics = set(item.topics or [])
        if topic not in topics:
            continue
        for other in topics - {topic}:
            co[other] += 1
    return {
        "topic": topic,
        "related": [{"topic": t, "score": c} for t, c in co.most_common(10)],
    }


# Vercel Cron은 GET으로 호출한다. POST는 수동 실행용으로 함께 허용한다.
@router.api_route("/api/admin/refresh", methods=["GET", "POST"])
async def admin_refresh(
    request: Request,
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Bearer ADMIN_TOKEN으로 수동 수집 실행.

    입력:
      - request: Request
      - authorization: str | None
      - settings: Settings
    출력: dict
    결과: 3개 플랫폼 전체 수집 파이프라인 실행 후 Top1 푸시 발송. 완료까지 대기
    """
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    expected = settings.admin_token.get_secret_value()
    cron_expected = settings.cron_secret.get_secret_value()
    allowed = [t for t in (expected, cron_expected) if t]
    if not token or not any(hmac.compare_digest(token, t) for t in allowed):
        raise HTTPException(status_code=401, detail="unauthorized")

    await run_daily_collect(request.app.state.session_factory, settings)
    return {"status": "ok"}


@router.post("/api/push/subscribe")
async def push_subscribe(
    body: SubscribeBody,
    session: Session = Depends(get_session),
) -> dict:
    """

    입력:
      - body: SubscribeBody
      - session: Session
    출력: dict
    결과: push_subscriptions에 구독 upsert 후 커밋
    """
    from backend.push import subscribe

    subscribe(session, body.endpoint, body.keys)
    return {"status": "ok"}


@router.post("/api/push/unsubscribe")
async def push_unsubscribe(
    body: SubscribeBody,
    session: Session = Depends(get_session),
) -> dict:
    """

    입력:
      - body: SubscribeBody
      - session: Session
    출력: dict
    결과: 해당 endpoint 구독 삭제 후 커밋
    """
    from backend.push import unsubscribe

    unsubscribe(session, body.endpoint)
    return {"status": "ok"}


@router.get("/api/push/vapid-key")
async def vapid_key(settings: Settings = Depends(get_settings)) -> dict:
    """

    입력:
      - settings: Settings
    출력: dict
    결과: 없음 (공개키 조회)
    """
    return {"key": settings.vapid_public_key if settings.push_enabled else ""}


@router.get("/manifest.json")
async def manifest() -> FileResponse:
    """

    입력:
      - 없음
    출력: FileResponse
    결과: 없음 (정적 파일 응답)
    """
    return FileResponse(
        BASE_DIR / "static" / "manifest.json",
        media_type="application/manifest+json",
    )


@router.get("/sw.js")
async def service_worker() -> FileResponse:
    """

    입력:
      - 없음
    출력: FileResponse
    결과: 없음 (서비스워커 파일 응답)
    """
    return FileResponse(BASE_DIR / "static" / "sw.js", media_type="application/javascript")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """

    입력:
      - request: Request
    출력: HTMLResponse
    결과: 없음 (템플릿 렌더 응답)
    """
    settings: Settings = request.app.state.settings
    template = request.app.state.templates.get_template("index.html")
    return HTMLResponse(
        template.render(request=request, vapid_public_key=settings.vapid_public_key),
        headers={"Cache-Control": "no-cache"},
    )
