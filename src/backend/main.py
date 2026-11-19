"""FastAPI 앱 조립. DAIT의 create_app 패턴을 따른다."""

import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

# Vercel 서버리스는 이 파일을 패키지 컨텍스트 없이 직접 로드하므로
# src/를 sys.path에 추가해 `backend.*` 임포트가 동작하게 한다.
_SRC = str(Path(__file__).resolve().parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from starlette.concurrency import run_in_threadpool

from backend.config import Settings, get_settings
from backend.db import init_db, session_factory
from backend.routes import router
from backend.scheduler import start_scheduler, stop_scheduler

BASE_DIR = Path(__file__).resolve().parent


def create_app(settings: Settings | None = None) -> FastAPI:
    """FastAPI 앱을 조립한다.

    입력: settings — 테스트용 주입 설정 (None이면 get_settings())
    출력: 라우터·정적파일·lifespan이 연결된 FastAPI 인스턴스
    결과: app.state에 settings/session_factory/templates 저장,
        VERCEL env 없을 때만 APScheduler 기동
    """
    config = settings if settings is not None else get_settings()
    docs = config.app_env == "debug"

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        await run_in_threadpool(init_db)
        factory = session_factory()
        app.state.session_factory = factory
        # Vercel serverless는 요청 사이에 인스턴스가 동결되어 APScheduler가
        # 신뢰성 있게 동작하지 않는다. 수집은 vercel.json Cron이 담당한다.
        # (Render 같은 상시 서버에서는 VERCEL env가 없어 정상 동작)
        if not os.environ.get("VERCEL"):
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


def _make_templates() -> Environment:
    """Jinja2 템플릿 환경을 만든다.

    입력: 없음 (BASE_DIR/templates 사용)
    출력: autoescape가 켜진 jinja2.Environment
    결과: index.html 등 템플릿 로드 가능 상태
    """
    return Environment(loader=FileSystemLoader(str(BASE_DIR / "templates")), autoescape=True)


app = create_app()
