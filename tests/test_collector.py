"""collector: dedupe, archived/fork 제외, 스냅샷 저장, 캐시 재사용."""

from datetime import date

import pytest

from backend.collector import collect_platform
from backend.github_client import RepoHit
from backend.models import Snapshot, SnapshotItem
from backend.summarizer import content_hash


class FakeGitHub:
    def __init__(self, hits_by_query):
        self.hits_by_query = hits_by_query
        self.readme_calls = []

    async def search_repositories(self, query, per_page=30):
        return self.hits_by_query.get(query, [])

    async def fetch_readme(self, full_name):
        self.readme_calls.append(full_name)
        return f"README for {full_name}"

    async def aclose(self):
        pass


class FakeSummarizer:
    def __init__(self):
        self.calls = []

    async def summarize(self, platform, full_name, description, readme):
        self.calls.append(full_name)
        return {
            "en": ["en1", "en2", "en3"],
            "zh": ["zh1", "zh2", "zh3"],
            "ko": ["ko1", "ko2", "ko3"],
        }

    async def aclose(self):
        pass


def _hit(name, stars, **kw):
    return RepoHit(
        full_name=name,
        html_url=f"https://github.com/{name}",
        description=kw.get("description", f"desc {name}"),
        stars=stars,
        language=kw.get("language", "Python"),
        topics=kw.get("topics", ["ai"]),
    )


@pytest.fixture()
def claude_queries(settings):
    return settings.platform_queries()["claude"]


@pytest.mark.asyncio
async def test_collect_dedupes_and_ranks(db_session, settings, claude_queries):
    q = claude_queries[0]
    gh = FakeGitHub(
        {
            q: [
                _hit("a/one", 100),
                _hit("a/one", 200),  # 중복 → 높은 star 쪽 유지
                _hit("a/two", 50),
            ]
        }
    )
    sm = FakeSummarizer()
    snap = await collect_platform(
        "claude", db_session, settings, github=gh, summarizer=sm,
        collected_date=date(2026, 11, 18),
    )
    assert snap.platform == "claude"
    items = sorted(snap.items, key=lambda i: i.rank)
    assert [i.repo_full_name for i in items] == ["a/one", "a/two"]
    assert items[0].stars == 200
    assert items[0].summary_ko == ["ko1", "ko2", "ko3"]
    # 중복 제거 후 README는 repo당 1회
    assert gh.readme_calls.count("a/one") == 1


@pytest.mark.asyncio
async def test_collect_excludes_archived_and_fork(db_session, settings):
    q = settings.platform_queries()["claude"][0]
    archived = _hit("a/arch", 999)
    archived.archived = True
    fork = _hit("a/fork", 998)
    fork.fork = True
    gh = FakeGitHub({q: [archived, fork, _hit("a/ok", 10)]})
    snap = await collect_platform(
        "claude", db_session, settings, github=gh, summarizer=FakeSummarizer(),
        collected_date=date(2026, 11, 18),
    )
    assert [i.repo_full_name for i in snap.items] == ["a/ok"]


@pytest.mark.asyncio
async def test_collect_is_idempotent_for_same_date(db_session, settings):
    q = settings.platform_queries()["claude"][0]
    gh = FakeGitHub({q: [_hit("a/one", 100)]})
    d = date(2026, 11, 18)
    await collect_platform("claude", db_session, settings, github=gh,
                           summarizer=FakeSummarizer(), collected_date=d)
    snap2 = await collect_platform("claude", db_session, settings, github=gh,
                                   summarizer=FakeSummarizer(), collected_date=d)
    count = db_session.query(Snapshot).filter_by(platform="claude").count()
    assert count == 1
    assert len(snap2.items) == 1


@pytest.mark.asyncio
async def test_stars_today_uses_previous_snapshot(db_session, settings):
    q = settings.platform_queries()["claude"][0]
    gh1 = FakeGitHub({q: [_hit("a/one", 100)]})
    await collect_platform("claude", db_session, settings, github=gh1,
                           summarizer=FakeSummarizer(), collected_date=date(2026, 11, 17))
    gh2 = FakeGitHub({q: [_hit("a/one", 130)]})
    snap = await collect_platform("claude", db_session, settings, github=gh2,
                                  summarizer=FakeSummarizer(), collected_date=date(2026, 11, 18))
    assert snap.items[0].stars_today == 30


@pytest.mark.asyncio
async def test_summary_cache_reused_for_same_hash(db_session, settings):
    q = settings.platform_queries()["claude"][0]
    sm = FakeSummarizer()
    d1, d2 = date(2026, 11, 17), date(2026, 11, 18)
    gh = FakeGitHub({q: [_hit("a/one", 100, description="same desc")]})
    await collect_platform("claude", db_session, settings, github=gh, summarizer=sm, collected_date=d1)
    calls_after_first = len(sm.calls)
    await collect_platform("claude", db_session, settings, github=gh, summarizer=sm, collected_date=d2)
    # README도 동일 → content_hash 동일 → LLM 재호출 없어야 함
    assert len(sm.calls) == calls_after_first


@pytest.mark.asyncio
async def test_llm_failure_translates_ko_when_enabled(db_session, settings, monkeypatch):
    """translate_fallback=True이면 LLM 실패 시 한국어를 Google 번역으로 변환한다."""
    settings = settings.model_copy(update={"translate_fallback": True})

    async def fake_translate(text):
        return f"[KO]{text}"

    monkeypatch.setattr("backend.summarizer.translate_ko", fake_translate)
    # collector는 모듈 레벨에서 import한 함수를 쓰므로 summarizer 쪽을 패치
    import backend.collector as collector_mod

    # fallback_summaries_async 내부에서 translate_ko를 참조하므로 summarizer 모듈 패치로 충분
    q = settings.platform_queries()["claude"][0]

    class BadSummarizer(FakeSummarizer):
        async def summarize(self, *a, **k):
            raise RuntimeError("llm down")

    gh = FakeGitHub({q: [_hit("a/one", 10, description="English description")]})
    snap = await collect_platform("claude", db_session, settings, github=gh,
                                  summarizer=BadSummarizer(), collected_date=date(2026, 11, 18))
    item = snap.items[0]
    assert item.summary_en[0] == "English description"
    assert item.summary_ko[0].startswith("[KO]")


@pytest.mark.asyncio
async def test_llm_failure_still_collects(db_session, settings):
    q = settings.platform_queries()["claude"][0]

    class BadSummarizer(FakeSummarizer):
        async def summarize(self, *a, **k):
            raise RuntimeError("llm down")

    gh = FakeGitHub({q: [_hit("a/one", 10, description="fallback desc")]})
    snap = await collect_platform("claude", db_session, settings, github=gh,
                                  summarizer=BadSummarizer(), collected_date=date(2026, 11, 18))
    item = snap.items[0]
    assert item.summary_en[0] == "fallback desc"
