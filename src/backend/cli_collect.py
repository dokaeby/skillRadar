"""일회성 수집 CLI. Render Cron Job 등에서 `python -m backend.cli_collect`로 실행."""

import asyncio
import logging

from backend.collector import collect_all
from backend.config import get_settings
from backend.db import init_db, session_factory
from backend.push import notify_daily_top

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def main() -> None:
    """일회성 수집 실행: 전체 플랫폼 수집 후 Top1 푸시 발송.

    입력: 없음 (환경변수/설정 파일에서 읽음)
    출력: 없음
    결과: 스냅샷 저장 + push_subscriptions 구독자에게 알림 발송
    """
    settings = get_settings()
    init_db()
    factory = session_factory()
    await collect_all(factory, settings, force=True)
    session = factory()
    try:
        await notify_daily_top(session, settings)
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
