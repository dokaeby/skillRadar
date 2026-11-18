"""API + 서버 렌더링 라우트."""

import logging
from datetime import date as date_type
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import PLATFORMS, Settings, get_settings
from app.db import get_session
from app.github_client import today_kst
from app.models import Snapshot
from app.scheduler import run_daily_collect

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


class TrendingResponse(BaseModel):
    platform: str
    date: str
    items: list[TrendingItem]


class SubscribeBody(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    keys: dict[str, str]


def _serialize_item(item, lang: str) -> TrendingItem:
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
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")

    await run_daily_collect(request.app.state.session_factory, settings)
    return {"status": "ok"}


@router.post("/api/push/subscribe")
async def push_subscribe(
    body: SubscribeBody,
    session: Session = Depends(get_session),
) -> dict:
    from app.push import subscribe

    subscribe(session, body.endpoint, body.keys)
    return {"status": "ok"}


@router.post("/api/push/unsubscribe")
async def push_unsubscribe(
    body: SubscribeBody,
    session: Session = Depends(get_session),
) -> dict:
    from app.push import unsubscribe

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
