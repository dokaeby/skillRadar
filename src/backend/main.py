"""FastAPI 앱 조립. DAIT의 create_app 패턴을 따른다."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from backend.config import Settings, get_settings
from backend.db import get_engine, init_db, session_factory
from backend.routes import router
from backend.scheduler import start_scheduler, stop_scheduler

BASE_DIR = Path(__file__).resolve().parent


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else get_settings()
    docs = config.app_env == "debug"

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        await run_in_threadpool(init_db)
        factory = session_factory()
        app.state.session_factory = factory
        start_scheduler(factory, config)
        yield
        stop_scheduler()

    app = FastAPI(
        lifespan=lifespan,
        title="SkillRadar",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.settings = config
    app.state.templates = _make_templates()
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    return app


def _make_templates():
    from jinja2 import Environment, FileSystemLoader

    return Environment(loader=FileSystemLoader(str(BASE_DIR / "templates")), autoescape=True)


app = create_app()
