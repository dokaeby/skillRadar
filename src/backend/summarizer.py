"""LLM 기반 3줄 요약 생성. JSON 강제, 캐시, 재시도, description 폴백."""

import asyncio
import hashlib
import json
import logging
import re

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

PROMPT = """You summarize GitHub repositories for {platform} AI-tooling users.

Rules:
- Output ONLY a JSON object, no markdown, no explanation.
- Exactly 3 lines per language, one sentence each.
- English lines: max 120 chars each.
- Keep technical terms (MCP, plugin, skill, CLI) in original form.
- Write natural UTF-8 text; do NOT use \\uXXXX unicode escapes.
- Order: (1) what it does, (2) how to use / key features, (3) target users or notable traits.
- No hype, marketing phrases, or superlatives.

Repository:
- name: {name}
- description: {description}
- README excerpt:
{readme}

Return this exact JSON shape:
{{
  "summary_en": ["...", "...", "..."],
  "summary_zh": ["...", "...", "..."],
  "summary_ko": ["...", "...", "..."]
}}"""

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


# JSON 문자열 안의 \uXXXX 유니코드 이스케이프 처리.
# Gemini(flash-lite)가 한/중 문자를 \uXXXX로 출력하고 가끔 깨진 이스케이프를 만든다.
_VALID_U = re.compile(r"(?<!\\)\\u([0-9a-fA-F]{4})")
_BAD_U = re.compile(r"(?<!\\)\\u(?![0-9a-fA-F]{4})")
_LITERAL_U = re.compile(r"\\u([0-9a-fA-F]{4})")
_STRAY_U = re.compile(r"\\u")


def _preclean_block(block: str) -> str:
    """파싱 전: 유효한 \\uXXXX를 실제 문자로 바꾸고 깨진 \\u는 제거한다.

    입력:
      - block: str
    출력: str
    결과: 없음 (순수 텍스트 처리)
    """
    block = _VALID_U.sub(lambda m: chr(int(m.group(1), 16)), block)
    return _BAD_U.sub("", block)


def _decode_line_text(s: str) -> str:
    """파싱 후: 문자열에 남은 리터럴 \\uXXXX를 디코딩하고 깨진 \\u는 제거.

    입력:
      - s: str
    출력: str
    결과: 없음 (순수 텍스트 처리)
    """
    s = _LITERAL_U.sub(lambda m: chr(int(m.group(1), 16)), s)
    return _STRAY_U.sub("", s)


def _loads_lenient(block: str) -> object:
    """

    입력:
      - block: str
    출력: object — 파싱된 JSON 값 또는 None
    결과: 없음 (파싱 헬퍼)
    """
    for candidate in (block, _preclean_block(block)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            continue
    return None


def _extract_json(text: str) -> dict | None:
    # 1) 코드 펜스로 감싼 JSON 우선
    """

    입력:
      - text: str
    출력: dict | None
    결과: 없음 (파싱 헬퍼)
    """
    for m in _FENCE.finditer(text or ""):
        data = _loads_lenient(m.group(1))
        if isinstance(data, dict):
            return data
    # 2) 본문 내 첫 { ... } 블록
    match = _JSON_BLOCK.search(text or "")
    if not match:
        return None
    data = _loads_lenient(match.group(0))
    return data if isinstance(data, dict) else None


def content_hash(description: str | None, readme: str | None) -> str:
    """요약 캐시 키. description+README가 같으면 재요약하지 않는다.

    입력:
      - description: str | None
      - readme: str | None
    출력: str
    결과: 없음 (해시 계산)
    """
    raw = f"{description or ''}\n---\n{(readme or '')[:3000]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class LLMSummary(BaseModel):
    """LLM 구조화 출력 스키마. 언어별 정확히 3줄."""

    summary_en: list[str] = Field(min_length=3, max_length=3)
    summary_zh: list[str] = Field(min_length=3, max_length=3)
    summary_ko: list[str] = Field(min_length=3, max_length=3)


_INJECTION_RE = re.compile(
    r"ignore\s+(all|any|previous|above)\s+instructions|system\s+prompt|"
    r"you\s+are\s+now|do\s+not\s+follow|disregard\s+(all|any|previous)",
    re.IGNORECASE,
)


def sanitize_readme(text: str | None, max_chars: int = 3000) -> str:
    """README를 LLM 입력용으로 정제한다.

    입력:
      - text: str | None
      - max_chars: int
    출력: str
    결과: 없음 (정제 결과 문자열 반환)
    """
    if not text:
        return ""
    kept = [line for line in text.splitlines() if not _INJECTION_RE.search(line)]
    return "\n".join(kept)[:max_chars]


def _normalize(data: dict) -> dict[str, list[str]] | None:
    """LLM 응답을 {en, zh, ko: [3줄]} 형태로 정규화한다.

    입력:
      - data: dict — _extract_json이 반환한 파싱 결과
    출력: dict[str, list[str]] | None — 정규화 실패 시 None
    결과: LLMSummary 스키마 검증까지 통과한 3언어 요약 dict 반환
    """
    out: dict[str, list[str]] = {}
    for key, field_name in (("en", "summary_en"), ("zh", "summary_zh"), ("ko", "summary_ko")):
        lines = data.get(field_name)
        if not isinstance(lines, list):
            return None
        cleaned = [_decode_line_text(str(x)).strip() for x in lines if str(x).strip()][:3]
        if len(cleaned) != 3:
            return None
        out[key] = cleaned
    try:
        validated = LLMSummary.model_validate(
            {
                "summary_en": out["en"],
                "summary_zh": out["zh"],
                "summary_ko": out["ko"],
            }
        )
    except Exception:
        return None
    return {
        "en": validated.summary_en,
        "zh": validated.summary_zh,
        "ko": validated.summary_ko,
    }


def fallback_summaries(description: str | None, full_name: str) -> dict[str, list[str]]:
    """LLM 실패 시 description 원문으로 대체 (3줄 보장).

    입력:
      - description: str | None
      - full_name: str
    출력: dict[str, list[str]]
    결과: 없음 (description 기반 폴백 생성)
    """
    base = (description or full_name).strip()
    lines = [base]
    while len(lines) < 3:
        lines.append(full_name)
    return {"en": lines[:3], "zh": lines[:3], "ko": lines[:3]}


_translate_sem: "asyncio.Semaphore | None" = None
_TRANSLATE_INTERVAL = 1.1  # Google 무료 번역 한도(초당 ~5회)보다 충분히 낮게
_google_broken = False  # 연속 실패 시 Google을 건너뛰는 서킷 브레이커


def _get_translate_sem() -> "asyncio.Semaphore":
    """

    입력:
      - 없음
    출력: 'asyncio.Semaphore'
    결과: 없음 (세마포어 지연 생성)
    """
    global _translate_sem
    if _translate_sem is None:
        _translate_sem = asyncio.Semaphore(1)
    return _translate_sem


async def _try_google(text: str) -> str:
    """

    입력:
      - text: str
    출력: str
    결과: Google 번역 API 호출. 실패 시 빈 문자열
    """
    global _google_broken
    from deep_translator import GoogleTranslator

    for attempt in range(3):
        try:
            async with _get_translate_sem():
                await asyncio.sleep(_TRANSLATE_INTERVAL)
                result = await asyncio.to_thread(
                    GoogleTranslator(source="auto", target="ko").translate, text
                )
            _google_broken = False
            return result
        except Exception:
            if attempt == 2:
                _google_broken = True
                raise
            await asyncio.sleep(15)
    raise RuntimeError("unreachable")


async def translate_ko(text: str) -> str:
    """Google 번역 우선, rate limit/차단 시 MyMemory 폴백. 최종 실패 시 원문 반환.

    입력:
      - text: str
    출력: str
    결과: 없음 (번역 결과 문자열)
    """
    global _google_broken
    if not _google_broken:
        try:
            return await _try_google(text)
        except Exception as exc:
            logger.info("Google 번역 실패, MyMemory 폴백 시도: %s", exc)
    try:
        from deep_translator import MyMemoryTranslator

        async with _get_translate_sem():
            await asyncio.sleep(_TRANSLATE_INTERVAL)
            result = await asyncio.to_thread(
                MyMemoryTranslator(source="en-US", target="ko-KR").translate, text
            )
            return result if isinstance(result, str) else " ".join(result)
    except Exception as exc:  # noqa: BLE001 - 번역 실패가 수집을 막으면 안 됨
        logger.info("한국어 번역 폴백 실패, 원문 사용: %s", exc)
        return text


async def translate_lines_ko(lines: list[str]) -> list[str]:
    """3줄 요약을 한 번의 번역 호출로 변환. 줄 수가 어긋나면 개별 번역.

    입력:
      - lines: list[str]
    출력: list[str]
    결과: 없음 (행별 번역 결과 리스트)
    """
    joined = "\n".join(lines)
    out = await translate_ko(joined)
    parts = [p.strip() for p in out.split("\n") if p.strip()]
    if len(parts) == len(lines):
        return parts
    return [await translate_ko(line) for line in lines]


async def fallback_summaries_async(
    description: str | None, full_name: str
) -> dict[str, list[str]]:
    """LLM 실패 시 description 폴백 + 한국어는 Google 번역으로 변환.

    입력:
      - description: str | None
      - full_name: str
    출력: dict[str, list[str]]
    결과: 없음 (폴백 요약 dict)
    """
    fb = fallback_summaries(description, full_name)
    fb["ko"] = await translate_lines_ko(fb["en"])
    return fb


_llm_sem: "asyncio.Semaphore | None" = None


def _get_llm_sem() -> "asyncio.Semaphore":
    """

    입력:
      - 없음
    출력: 'asyncio.Semaphore'
    결과: 없음 (세마포어 지연 생성)
    """
    global _llm_sem
    if _llm_sem is None:
        _llm_sem = asyncio.Semaphore(1)
    return _llm_sem


class Summarizer:
    """OpenAI-호환 chat/completions 엔드포인트를 호출하는 요약기."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
        min_interval: float = 0.0,
    ) -> None:
        """

        입력:
          - api_key: str
          - base_url: str
          - model: str
          - client: httpx.AsyncClient | None
          - timeout: float
          - min_interval: float
        출력: 없음
        결과: Summarizer 인스턴스 상태 초기화 (LLM/번역 클라이언트)
        """
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._min_interval = min_interval

    async def aclose(self) -> None:
        """

        입력:
          - 없음
        출력: 없음
        결과: httpx 클라이언트 연결 해제
        """
        await self._client.aclose()

    async def summarize(
        self, platform: str, full_name: str, description: str | None, readme: str
    ) -> dict[str, list[str]]:
        """3개 언어 3줄 요약을 반환. 파싱 실패 시 1회 재시도, 그래도 실패하면 폴백.

        입력:
          - platform: str
          - full_name: str
          - description: str | None
          - readme: str
        출력: dict[str, list[str]]
        결과: LLM으로 3개 언어 요약 생성 + 한국어 번역. 실패 시 폴백
        """
        prompt = PROMPT.format(
            platform=platform,
            name=full_name,
            description=description or "(none)",
            readme=(readme or "(empty)")[:3000],
        )
        for attempt in range(3):
            last = attempt == 2
            try:
                async with _get_llm_sem():
                    if self._min_interval:
                        await asyncio.sleep(self._min_interval)
                    resp = await self._client.post(
                        self._url,
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self._model,
                            "temperature": 0.2,
                            "messages": [{"role": "user", "content": prompt}],
                        },
                    )
                    resp.raise_for_status()
                    content = resp.json()["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                logger.warning("LLM 호출 실패 %s (%s): %s", full_name, status, exc)
                if last:
                    return await fallback_summaries_async(description, full_name)
                # 429/503은 무료 티어 rate limit·수요 초과 → 잠시 후 재시도
                await asyncio.sleep(20 if status in (429, 503) else 2)
                continue
            except Exception as exc:  # noqa: BLE001 - 항목별 예외 격리 원칙
                logger.warning("LLM 호출 실패 (%s): %s", full_name, exc)
                if last:
                    return await fallback_summaries_async(description, full_name)
                continue

            data = _extract_json(content or "")
            if data is None:
                logger.warning("LLM JSON 파싱 실패, 재시도: %s", full_name)
                if last:
                    return await fallback_summaries_async(description, full_name)
                continue
            normalized = _normalize(data)
            if normalized is None:
                logger.warning("LLM 요약 형식 오류, 재시도: %s", full_name)
                if last:
                    return await fallback_summaries_async(description, full_name)
                continue
            # flash-lite가 ko를 \uXXXX로 출력하다 깨지는 경우가 있어
            # ko에 한글이 없으면 en 라인을 Google 번역으로 생성한다.
            if not any("가" <= ch <= "힣" for line in normalized["ko"] for ch in line):
                normalized["ko"] = await translate_lines_ko(normalized["en"])
            return normalized
        return await fallback_summaries_async(description, full_name)
