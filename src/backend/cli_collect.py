"""일회성 수집 CLI. Render Cron Job 등에서 `python -m backend.cli_collect`로 실행."""

import asyncio
import logging

from sqlalchemy.orm import sessionmaker

from backend.collector import collect_all
from backend.config import get_settings
from backend.db import get_engine, init_db, session_factory
from backend.push import notify_daily_top

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def main() -> None:
    settings = get_settings()
    init_db()
    factory = session_factory()
    session = factory()
    try:
        await collect_all(session, settings)
        await notify_daily_top(session, settings)
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
