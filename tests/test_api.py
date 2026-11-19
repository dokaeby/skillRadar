"""API·렌더링 테스트: /api/trending, /, admin refresh 인증."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import Settings
from backend.main import create_app
from backend.models import Base, Snapshot, SnapshotItem


@pytest.fixture()
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path}/api.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # 스케줄러는 테스트에서 끈다
    monkeypatch.setattr("backend.main.start_scheduler", lambda *a, **k: None)
    monkeypatch.setattr("backend.main.stop_scheduler", lambda: None)

    settings = type("S", (), {})()  # placeholder replaced below
    settings = Settings(
        app_env="debug",
        database_url=f"sqlite:///{tmp_path}/api.db",
        admin_token=SecretStr("secret-admin"),
        cron_secret=SecretStr("secret-cron"),
        github_token=SecretStr(""),
        llm_api_key=SecretStr(""),
        vapid_public_key="",
        vapid_private_key=SecretStr(""),
    )
    app = create_app(settings)
    app.state.session_factory = factory

    # get_session dependency를 테스트 팩토리로 교체
    from backend.db import get_session

    def override_get_session():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as c:
        yield c, factory
    engine.dispose()


def _seed(factory, platform="claude", d=date(2026, 11, 18)):
    s = factory()
    snap = Snapshot(platform=platform, collected_date=d)
    s.add(snap)
    s.flush()
    s.add(
        SnapshotItem(
            snapshot_id=snap.id,
            rank=1,
            repo_full_name="owner/top-repo",
            repo_url="https://github.com/owner/top-repo",
            description="Top repo description",
            stars=1234,
            stars_today=56,
            language="Python",
            topics=["mcp", "skills"],
            summary_en=["en1", "en2", "en3"],
            summary_zh=["zh1", "zh2", "zh3"],
            summary_ko=["ko1", "ko2", "ko3"],
            content_hash="x" * 64,
        )
    )
    s.commit()
    s.close()


def test_index_renders(client):
    c, _ = client
    res = c.get("/")
    assert res.status_code == 200
    assert "SkillRadar" in res.text
    assert "Claude" in res.text


def test_trending_returns_items(client):
    c, factory = client
    _seed(factory)
    res = c.get("/api/trending?platform=claude&lang=ko&date=2026-11-18")
    assert res.status_code == 200
    data = res.json()
    assert data["platform"] == "claude"
    assert data["items"][0]["repo_full_name"] == "owner/top-repo"
    assert data["items"][0]["summary"] == ["ko1", "ko2", "ko3"]
    assert data["items"][0]["stars_today"] == 56


def test_trending_lang_en(client):
    c, factory = client
    _seed(factory)
    res = c.get("/api/trending?platform=claude&lang=en")
    assert res.json()["items"][0]["summary"] == ["en1", "en2", "en3"]


def test_trending_empty_when_no_data(client):
    c, _ = client
    res = c.get("/api/trending?platform=gemini")
    assert res.status_code == 200
    assert res.json()["items"] == []


def test_trending_bad_platform(client):
    c, _ = client
    assert c.get("/api/trending?platform=nope").status_code == 400


def test_trending_bad_date(client):
    c, _ = client
    assert c.get("/api/trending?platform=claude&date=not-a-date").status_code == 400


def test_admin_refresh_requires_token(client):
    c, _ = client
    assert c.post("/api/admin/refresh").status_code == 401
    resp = c.post(
        "/api/admin/refresh", headers={"Authorization": "Bearer wrong"}
    )
    assert resp.status_code == 401
    # Vercel Cron은 GET으로 호출한다
    assert c.get("/api/admin/refresh").status_code == 401
    assert c.get("/api/admin/refresh", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_admin_refresh_accepts_admin_and_cron_token(client, monkeypatch):
    c, _ = client

    async def fake_collect(factory, settings, force=False):
        return []

    monkeypatch.setattr("backend.routes.run_daily_collect", fake_collect)
    # get_session과 마찬가지로 get_settings도 테스트 설정으로 교체한다
    from backend.config import get_settings

    c.app.dependency_overrides[get_settings] = lambda: c.app.state.settings
    for token in ("secret-admin", "secret-cron"):
        res = c.get("/api/admin/refresh", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}
        res = c.post("/api/admin/refresh", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200


def test_dates_endpoint(client):
    c, factory = client
    _seed(factory)
    res = c.get("/api/dates?platform=claude")
    assert res.status_code == 200
    assert "2026-11-18" in res.json()["dates"]
