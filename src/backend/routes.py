"""API + 서버 렌더링 라우트."""

import hmac
import logging
from collections import Counter
from datetime import date as date_type, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
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


def _serialize_item(item, lang: str, platform: str | None = None) -> TrendingItem:
    return TrendingItem(
        rank=item.rank,
        repo_full_name=item.repo_full_name,
        repo_url=item.repo_url,
        description=item.description,
        stars=item.stars,
        stars_today=item.stars_today,
        language=item.language,
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
    return session.execute(
        select(Snapshot)
        .where(Snapshot.platform == platform, Snapshot.collected_date == collected)
        .options()
    ).scalar_one_or_none()


@router.get("/api/trending", response_model=TrendingResponse)
async def trending(
    platform: str = "claude",
    date: str | None = None,
    lang: str = "ko",
    session: Session = Depends(get_session),
) -> TrendingResponse:
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail="platform은 claude|chatgpt|gemini 중 하나")
    if lang not in ("ko", "en", "zh"):
        raise HTTPException(status_code=400, detail="lang은 ko|en|zh 중 하나")
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
        items=[_serialize_item(i, lang) for i in snap.items],
    )


@router.get("/api/dates")
async def available_dates(
    platform: str = "claude",
    session: Session = Depends(get_session),
) -> dict:
    rows = session.execute(
        select(Snapshot.collected_date)
        .where(Snapshot.platform == platform)
        .order_by(Snapshot.collected_date.desc())
        .limit(30)
    ).scalars().all()
    return {"dates": [d.isoformat() for d in rows]}


TOPIC_WINDOW_DAYS = 30
TOPIC_MAX_RESULTS = 50


def _recent_items(session: Session):
    """최근 TOPIC_WINDOW_DAYS일 스냅샷의 (item, platform) 목록."""
    since = date_type.today() - timedelta(days=TOPIC_WINDOW_DAYS)
    return session.execute(
        select(SnapshotItem, Snapshot.platform)
        .join(Snapshot, SnapshotItem.snapshot_id == Snapshot.id)
        .where(Snapshot.collected_date >= since)
    ).all()


@router.get("/api/topics")
async def topics(session: Session = Depends(get_session)) -> dict:
    """최근 수집분에서 등장 횟수가 많은 GitHub 토픽을 관심순으로 반환."""
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
    """특정 토픽을 가진 저장소를 스타 순으로 반환 (플랫폼별 필터 가능)."""
    if not topic or len(topic) > 100:
        raise HTTPException(status_code=400, detail="topic 파라미터가 필요합니다")
    if platform != "all" and platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail="platform은 all|claude|chatgpt|gemini")
    if lang not in ("ko", "en", "zh"):
        raise HTTPException(status_code=400, detail="lang은 ko|en|zh 중 하나")
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
    """특정 토픽과 함께 등장한 다른 토픽을 공기반 점수 순으로 반환."""
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


@router.post("/api/admin/refresh")
async def admin_refresh(
    request: Request,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Bearer ADMIN_TOKEN으로 수동 수집 실행."""
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    expected = settings.admin_token.get_secret_value()
    if not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="unauthorized")

    await run_daily_collect(request.app.state.session_factory, settings)
    return {"status": "ok"}


@router.post("/api/push/subscribe")
async def push_subscribe(
    body: SubscribeBody,
    session: Session = Depends(get_session),
) -> dict:
    from backend.push import subscribe

    subscribe(session, body.endpoint, body.keys)
    return {"status": "ok"}


@router.post("/api/push/unsubscribe")
async def push_unsubscribe(
    body: SubscribeBody,
    session: Session = Depends(get_session),
) -> dict:
    from backend.push import unsubscribe

    unsubscribe(session, body.endpoint)
    return {"status": "ok"}


@router.get("/api/push/vapid-key")
async def vapid_key(settings: Settings = Depends(get_settings)) -> dict:
    return {"key": settings.vapid_public_key if settings.push_enabled else ""}


@router.get("/manifest.json")
async def manifest() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "manifest.json", media_type="application/manifest+json")


@router.get("/sw.js")
async def service_worker() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "sw.js", media_type="application/javascript")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    template = request.app.state.templates.get_template("index.html")
    return HTMLResponse(
        template.render(request=request, vapid_public_key=settings.vapid_public_key)
    )
