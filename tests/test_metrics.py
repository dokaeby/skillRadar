"""metrics_scope 지표 집계 단위 테스트."""

from backend import metrics as m


def test_scope_aggregates_counters():
    """스코프 안에서 기록한 카운터가 metrics_dict에 반영된다."""
    with m.metrics_scope() as met:
        m.record_llm_attempt(is_retry=False)
        m.record_llm_attempt(is_retry=True)
        m.record_llm_success(was_retry=True)
        m.record_verify(ok=True)
        m.record_verify(ok=False)
        m.record_fallback()
        m.record_cache_hit("classify")
        m.record_cache_hit("summarize")
        m.record_cache_hit("verify")
        m.record_repos(10)
        m.record_duration_ms(1234)

    assert met.llm_calls == 2
    assert met.llm_retries == 1
    assert met.llm_retry_successes == 1
    assert met.verify_calls == 2
    assert met.verify_passed == 1
    assert met.summary_fallbacks == 1
    assert met.cache_hits_classify == 1
    assert met.cache_hits_summarize == 1
    assert met.cache_hits_verify == 1
    assert met.repos_processed == 10
    assert met.duration_ms == 1234

    data = m.metrics_dict(met)
    assert data["retry_rate"] == 0.5
    assert data["retry_success_rate"] == 1.0
    assert data["unsupported_claim_rate"] == 0.5
    assert data["fidelity_score"] == 0.5


def test_outside_scope_is_noop():
    """스코프 밖에서는 기록이 무시되고 예외가 없다."""
    m.record_llm_attempt(is_retry=True)
    m.record_verify(ok=False)
    m.record_fallback()
    m.record_cache_hit("classify")
    m.record_repos(3)


def test_empty_scope_metrics_dict():
    """호출 0건이면 파생 지표는 None."""
    with m.metrics_scope() as met:
        pass
    data = m.metrics_dict(met)
    assert data["retry_rate"] is None
    assert data["retry_success_rate"] is None
    assert data["unsupported_claim_rate"] is None
    assert data["fidelity_score"] is None


def test_nested_scope_uses_innermost():
    """중첩 스코프는 안쪽 객체에만 기록된다."""
    with m.metrics_scope() as outer:
        m.record_llm_attempt(is_retry=False)
        with m.metrics_scope() as inner:
            m.record_llm_attempt(is_retry=False)
        assert inner.llm_calls == 1
    assert outer.llm_calls == 1
    assert inner.llm_calls == 1


def test_snapshot_metrics_column_exists(db_session):
    """Snapshot 모델에 metrics_json 컬럼이 마이그레이션된다."""
    from sqlalchemy import inspect

    from backend.db import get_engine

    cols = {c["name"] for c in inspect(get_engine()).get_columns("snapshots")}
    assert "metrics_json" in cols
    # ORM 객체에 저장 가능
    from datetime import date

    from backend.models import Snapshot

    snap = Snapshot(
        platform="claude",
        collected_date=date(2026, 1, 1),
        metrics_json={"llm_calls": 5, "fidelity_score": 0.9},
    )
    db_session.add(snap)
    db_session.commit()
    assert snap.metrics_json is not None
    assert snap.metrics_json["llm_calls"] == 5
    db_session.delete(snap)
    db_session.commit()


def test_tracing_noop_without_keys(monkeypatch):
    """Langfuse 키가 없으면 llm_span이 None을 yield한다."""
    from backend import tracing

    with tracing.llm_span("test", model="m", input_text="x") as obs:
        assert obs is None
    assert tracing.tracing_enabled() is False


def test_metrics_persisted_on_snapshot(db_session):
    """Snapshot.metrics_json에 지표 dict를 저장·조회할 수 있다."""
    from datetime import date

    from backend.models import Snapshot

    snap = Snapshot(
        platform="gemini",
        collected_date=date(2026, 1, 2),
        metrics_json=m.metrics_dict(m.RunMetrics(llm_calls=3)),
    )
    db_session.add(snap)
    db_session.commit()
    assert snap.metrics_json is not None
    assert snap.metrics_json["llm_calls"] == 3
    db_session.delete(snap)
    db_session.commit()


def test_metrics_dict_types():
    """metrics_dict 반환값이 JSON 직렬화 가능 타입이다."""
    import json

    with m.metrics_scope() as met:
        m.record_llm_attempt(is_retry=False)
        m.record_verify(ok=True)
    json.dumps(m.metrics_dict(met))  # 직렬화 실패 시 예외
    assert set(m.metrics_dict(met)) >= {
        "llm_calls",
        "verify_calls",
        "retry_rate",
        "fidelity_score",
    }

