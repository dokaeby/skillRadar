import os
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("APP_ENV", "debug")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_skillradar.db")
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("GITHUB_TOKEN", "")
os.environ.setdefault("LLM_API_KEY", "")


@pytest.fixture()
def db_session(tmp_path):
    """테스트용 임시 SQLite 세션."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.models import Base

    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def settings(tmp_path):
    from backend.config import Settings

    return Settings(
        app_env="debug",
        database_url=f"sqlite:///{tmp_path}/app.db",
        admin_token=SecretStr("test-admin-token"),
        github_token=SecretStr(""),
        llm_api_key=SecretStr(""),
        vapid_public_key="",
        vapid_private_key=SecretStr(""),
        translate_fallback=False,  # 테스트에서 외부 번역 API 호출 방지
    )
