"""매일 KST 06:00 수집 스케줄러 (APScheduler)."""

import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session, sessionmaker

from backend.collector import collect_all
from backend.config import PLATFORMS, Settings
from backend.github_client import today_kst
from backend.models import Snapshot
from backend.push import notify_daily_top, notify_weekly_digest, send_push

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def run_daily_collect(
    session_factory: sessionmaker[Session], settings: Settings, force: bool = False
) -> list[Snapshot]:
    """수집 + 푸시 알림. 스케줄러와 수동 refresh가 공용으로 쓴다.

    입력: session_factory — 플랫폼별 독립 세션을 만드는 팩토리;
        settings — GitHub/LLM/VAPID 설정; force — 같은 날짜 재수집 여부
    출력: list[Snapshot] — 플랫폼별 스냅샷 (스킵 시 기존 스냅샷)
    결과: 플랫폼 스냅샷 수집 후 실패 플랫폼이 있으면 실패 푸시 발송,
        이어서 Top1 푸시 발송
    """
    snapshots = await collect_all(session_factory, settings, force=force)
    session = session_factory()
    try:
        done = {snap.platform for snap in snapshots}
        failed = [p for p in PLATFORMS if p not in done]
        if failed:
            await send_push(
                session,
                settings,
                title="SkillRadar 수집 실패",
                body="수집 실패: " + ", ".join(p.capitalize() for p in failed),
                url="/",
            )
        await notify_daily_top(session, settings)
        # KST 월요일 수집분에는 주간 digest 푸시를 추가로 발송한다.
        if date.fromisoformat(today_kst()).weekday() == 0:
            await notify_weekly_digest(session, settings)
    finally:
        session.close()
    return snapshots


def start_scheduler(
    session_factory: sessionmaker[Session], settings: Settings
) -> AsyncIOScheduler | None:
    """앱 시작 시 호출. 이미 실행 중이면 그대로 반환한다.

    입력: session_factory — 수집 잡에 전달할 세션 팩토리;
        settings — schedule_hour/timezone 포함 설정
    출력: 실행 중인 AsyncIOScheduler (없으면 새로 생성해 반환)
    결과: 매일 schedule_hour:00에 run_daily_collect 잡 등록·시작
    """
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
    logger.info(
        "스케줄러 시작: 매일 %02d:00 %s",
        settings.schedule_hour,
        settings.schedule_timezone,
    )
    return sched


def stop_scheduler() -> None:
    """전역 스케줄러를 종료하고 참조를 지운다.

    입력: 없음
    출력: 없음
    결과: 실행 중이던 AsyncIOScheduler가 shutdown됨
    """
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
