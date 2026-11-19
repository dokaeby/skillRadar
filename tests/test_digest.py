"""주간 digest 푸시 집계 테스트."""

from datetime import date, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import Settings
from backend.models import Base, Snapshot, SnapshotItem
from backend.push import notify_weekly_digest


@pytest.fixture()
def factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/digest.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _settings(db_url: str = "sqlite:////tmp/digest_settings.db") -> Settings:
    return Settings(
        app_env="debug",
        database_url=db_url,
        admin_token=SecretStr("t"),
        github_token=SecretStr(""),
        llm_api_key=SecretStr(""),
        vapid_public_key="pub",
        vapid_private_key=SecretStr("priv"),
        vapid_subject="mailto:test@example.com",
    )


def _seed_item(factory, full_name, d, stars_today=10):
    s = factory()
    snap = Snapshot(platform="claude", collected_date=d)
    s.add(snap)
    s.flush()
    s.add(
        SnapshotItem(
            snapshot_id=snap.id,
            rank=1,
            repo_full_name=full_name,
            repo_url=f"https://github.com/{full_name}",
            stars=100,
            stars_today=stars_today,
            topics=[],
        )
    )
    s.commit()
    s.close()


@pytest.mark.asyncio
async def test_weekly_digest_disabled(factory):
    s = factory()
    settings = Settings(
        app_env="debug", database_url="sqlite:////tmp/digest_disabled.db",
        admin_token=SecretStr("t"), github_token=SecretStr(""), llm_api_key=SecretStr(""),
        vapid_public_key="", vapid_private_key=SecretStr(""),
    )
    assert await notify_weekly_digest(s, settings) == 0
    s.close()


@pytest.mark.asyncio
async def test_weekly_digest_body(factory, monkeypatch):
    today = date.today()
    _seed_item(factory, "owner/new-repo", today - timedelta(days=1), stars_today=42)
    _seed_item(factory, "owner/old-repo", today - timedelta(days=20), stars_today=5)
    _seed_item(factory, "owner/old-repo", today, stars_today=7)

    sent = {}

    async def fake_send(session, settings, title, body, url="/"):
        sent["title"] = title
        sent["body"] = body
        return 2

    monkeypatch.setattr("backend.push.send_push", fake_send)
    s = factory()
    assert await notify_weekly_digest(s, _settings()) == 2
    s.close()
    assert sent["title"] == "SkillRadar 주간 리포트"
    assert "신규 1개" in sent["body"]
    assert "이탈 0개" in sent["body"]
    assert "주간 star 증가 49" in sent["body"]  # 42 + 7


@pytest.mark.asyncio
async def test_weekly_digest_empty(factory, monkeypatch):
    async def fake_send(*a, **k):
        raise AssertionError("send_push should not be called")

    monkeypatch.setattr("backend.push.send_push", fake_send)
    s = factory()
    assert await notify_weekly_digest(s, _settings()) == 0
    s.close()
