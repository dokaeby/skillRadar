"""매일 KST 06:00 수집 스케줄러 (APScheduler)."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session, sessionmaker

from backend.collector import collect_all
from backend.config import Settings
from backend.push import notify_daily_top

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def run_daily_collect(session_factory: sessionmaker[Session], settings: Settings) -> None:
    """수집 + 푸시 알림. 스케줄러와 수동 refresh가 공용으로 쓴다."""
    await collect_all(session_factory, settings)
    session = session_factory()
    try:
        await notify_daily_top(session, settings)
    finally:
        session.close()


def start_scheduler(session_factory: sessionmaker[Session], settings: Settings) -> AsyncIOScheduler | None:
    """앱 시작 시 호출. 이미 실행 중이면 그대로 반환한다."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    sched = AsyncIOScheduler(timezone=settings.schedule_timezone)
    sched.add_job(
        run_daily_collect,
        CronTrigger(hour=settings.schedule_hour, minute=0, timezone=settings.schedule_timezone),
        args=[session_factory, settings],
        id="daily-collect",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    sched.start()
    _scheduler = sched
    logger.info("스케줄러 시작: 매일 %02d:00 %s", settings.schedule_hour, settings.schedule_timezone)
    return sched


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
