"""llm_tasks: 분류/검증/채점 프롬프트와 응답 파싱."""

import json

import httpx
import pytest

from backend.llm_tasks import classify_repo, judge_summary, verify_summary


def _client(payload: dict | None = None, status: int = 200):
    def handler(req: httpx.Request) -> httpx.Response:
        if payload is None:
            return httpx.Response(status, json={"error": "boom"})
        return httpx.Response(
            status,
            json={
                "choices": [
                    {"message": {"content": json.dumps(payload)}}
                ]
            },
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


KW = dict(api_key="k", base_url="https://llm.test/v1", model="gemini-3.5-flash-lite")


# --- classify_repo ---


@pytest.mark.asyncio
async def test_classify_success():
    client = _client({"label": "agents", "confidence": 0.9})
    result = await classify_repo(
        description="agent toolkit", readme="# A\nDoes agents.",
        name="a/b", topics=["agents"], client=client, **KW,
    )
    assert result.label == "agents"
    assert result.confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_classify_invalid_label_falls_back():
    client = _client({"label": "not-a-label", "confidence": 0.9})
    result = await classify_repo(
        description=None, readme="# x", name="a/b", topics=[], client=client, **KW,
    )
    assert result.label == "other"
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_classify_api_failure_falls_back():
    client = _client(status=500)
    result = await classify_repo(
        description=None, readme="# x", name="a/b", topics=[], client=client, **KW,
    )
    assert result.label == "other"
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_classify_clamps_confidence():
    client = _client({"label": "mcp", "confidence": 1.7})
    result = await classify_repo(
        description=None, readme="# x", name="a/b", topics=[], client=client, **KW,
    )
    assert result.label == "mcp"
    assert result.confidence == 1.0


# --- verify_summary ---


@pytest.mark.asyncio
async def test_verify_supported():
    client = _client({"supported": True})
    ok = await verify_summary(
        readme="# x", summary_lines=["Does X."], client=client, **KW,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_verify_unsupported():
    client = _client({"supported": False})
    ok = await verify_summary(
        readme="# x", summary_lines=["Claims Y."], client=client, **KW,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_verify_api_failure_returns_true():
    """검증기 장애가 파이프라인을 막지 않도록 실패 시 True."""
    client = _client(status=500)
    ok = await verify_summary(
        readme="# x", summary_lines=["Claims Y."], client=client, **KW,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_verify_bad_json_returns_true():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "no json here"}}]}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ok = await verify_summary(
        readme="# x", summary_lines=["Claims Y."], client=client, **KW,
    )
    assert ok is True


# --- judge_summary ---


@pytest.mark.asyncio
async def test_judge_score():
    client = _client({"score": 0.8})
    score = await judge_summary(
        readme="# x", summary_lines=["Does X."], client=client, **KW,
    )
    assert score == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_judge_clamps_out_of_range():
    client = _client({"score": 2.5})
    score = await judge_summary(
        readme="# x", summary_lines=["Does X."], client=client, **KW,
    )
    assert score == 1.0


@pytest.mark.asyncio
async def test_judge_failure_returns_sentinel():
    client = _client(status=500)
    score = await judge_summary(
        readme="# x", summary_lines=["Does X."], client=client, **KW,
    )
    assert score == -1.0


@pytest.mark.asyncio
async def test_judge_bad_score_returns_sentinel():
    client = _client({"score": "high"})
    score = await judge_summary(
        readme="# x", summary_lines=["Does X."], client=client, **KW,
    )
    assert score == -1.0
