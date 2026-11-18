"""summarizer: JSON 파싱, 재시도, 폴백, 캐시 키."""

import json

import httpx
import pytest

from backend.summarizer import (
    Summarizer,
    _extract_json,
    _normalize,
    content_hash,
    fallback_summaries,
)


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _no_real_translate(monkeypatch):
    """ko는 en 라인의 번역 결과이므로 Google 번역 호출을 목킹한다."""

    async def fake_translate(text: str) -> str:
        return "\n".join(f"[ko]{line}" for line in text.split("\n"))

    monkeypatch.setattr("backend.summarizer.translate_ko", fake_translate)


def _ok_response(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(payload)}}]},
    )


GOOD = {
    "summary_en": ["Does X for Y.", "Use it via Z.", "Built for devs."],
    "summary_zh": ["为Y做X。", "通过Z使用。", "面向开发者。"],
    "summary_ko": ["Y를 위한 X 도구.", "Z로 사용.", "개발자 대상."],
}


@pytest.mark.asyncio
async def test_summarize_returns_three_langs():
    sm = Summarizer(api_key="k", client=_client(lambda r: _ok_response(GOOD)))
    result = await sm.summarize("claude", "a/b", "desc", "readme")
    assert result["en"][0] == "Does X for Y."
    assert result["zh"][1] == "通过Z使用。"
    assert result["ko"][2] == "개발자 대상."


@pytest.mark.asyncio
async def test_summarize_retries_once_on_bad_json():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "not json at all"}}]}
            )
        return _ok_response(GOOD)

    sm = Summarizer(api_key="k", client=_client(handler))
    result = await sm.summarize("claude", "a/b", "desc", "readme")
    assert calls["n"] == 2
    assert result["en"][0] == "Does X for Y."


@pytest.mark.asyncio
async def test_summarize_falls_back_after_two_failures():
    sm = Summarizer(
        api_key="k",
        client=_client(lambda r: httpx.Response(500, text="err")),
    )
    result = await sm.summarize("claude", "a/b", "A tool for testing.", "readme")
    assert result["en"][0] == "A tool for testing."
    assert result["ko"][0] == "[ko]A tool for testing."
    assert len(result["ko"]) == 3


@pytest.mark.asyncio
async def test_summarize_falls_back_on_invalid_shape():
    bad = {"summary_en": ["only one"], "summary_zh": [], "summary_ko": []}
    sm = Summarizer(api_key="k", client=_client(lambda r: _ok_response(bad)))
    result = await sm.summarize("claude", "a/b", "desc text", "readme")
    assert result["en"][0] == "desc text"


def test_extract_json_with_surrounding_text():
    text = 'Here is the result: {"summary_en": ["a","b","c"]} hope it helps'
    data = _extract_json(text)
    assert data == {"summary_en": ["a", "b", "c"]}


def test_normalize_rejects_wrong_count():
    assert _normalize({"summary_en": ["a"], "summary_zh": ["b"], "summary_ko": ["c"]}, None) is None


def test_content_hash_stable_and_sensitive():
    h1 = content_hash("desc", "readme")
    h2 = content_hash("desc", "readme")
    h3 = content_hash("desc", "different")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_fallback_summaries_always_three_lines():
    fb = fallback_summaries(None, "owner/repo")
    assert all(len(v) == 3 for v in fb.values())
