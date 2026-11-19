"""GitHub Search/Contents API 클라이언트. rate limit·재시도·backoff 처리."""

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.github.com/search/repositories"
CONTENTS_URL = "https://api.github.com/repos/{full_name}/readme"
MAX_README_CHARS = 3000
KST = ZoneInfo("Asia/Seoul")


@dataclass
class RepoHit:
    full_name: str
    html_url: str
    description: str | None
    stars: int
    language: str | None
    topics: list[str] = field(default_factory=list)
    archived: bool = False
    fork: bool = False
    license: str | None = None  # SPDX id (MIT, Apache-2.0 등)


class GitHubClient:
    """인증 토큰과 재시도를 갖는 얇은 GitHub API 래퍼."""

    def __init__(
        self,
        token: str = "",
        client: httpx.AsyncClient | None = None,
        max_retries: int = 3,
        backoff_seconds: float = 2.0,
    ) -> None:
        self._token = token
        self._client = client or httpx.AsyncClient(timeout=20.0)
        self._max_retries = max_retries
        self._backoff = backoff_seconds

    async def aclose(self) -> None:
        """내부 httpx.AsyncClient를 닫는다.

        입력: 없음
        출력: 없음
        결과: 연결 풀 해제 — 사용 후 반드시 호출
        """
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        """GitHub API 공통 헤더 생성.

        입력: 없음 (self._token 사용)
        출력: Accept/API 버전 헤더 + 토큰 있으면 Authorization
        결과: 없음
        """
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _get_json(self, url: str, params: dict | None = None) -> dict | None:
        """rate limit(403/429)과 5xx에 대해 지수 backoff로 재시도한다.

        입력: url — GET 대상 API URL; params — 쿼리 파라미터
        출력: 200 응답의 JSON dict, 실패/한도 초과 시 None
        결과: 네트워크 오류·재시도 가능 상태코드는 최대 max_retries+1회 재시도,
            Retry-After 헤더 우선(최대 60초 대기)
        """
        delay = self._backoff
        for attempt in range(self._max_retries + 1):
            try:
                resp = await self._client.get(url, params=params, headers=self._headers())
            except httpx.HTTPError as exc:
                if attempt == self._max_retries:
                    logger.warning("GitHub 요청 네트워크 오류: %s", exc)
                    return None
                await asyncio.sleep(delay)
                delay *= 2
                continue

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (403, 429, 500, 502, 503):
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else delay
                if attempt == self._max_retries:
                    logger.warning("GitHub API %s 재시도 한도 초과", resp.status_code)
                    return None
                logger.info("GitHub API %s — %.1fs 후 재시도", resp.status_code, wait)
                await asyncio.sleep(min(wait, 60.0))
                delay *= 2
                continue
            logger.warning("GitHub API 오류 %s: %s", resp.status_code, resp.text[:200])
            return None
        return None

    async def search_repositories(
        self, query: str, per_page: int = 30
    ) -> list[RepoHit]:
        """쿼리 하나로 저장소 검색. archived/fork는 결과에서 제외한다.

        입력: query — GitHub search 쿼리 문자열; per_page — 최대 결과 수
        출력: RepoHit 리스트 (stars 내림차순, archived/fork 제외)
        결과: API 실패 시 빈 리스트 반환 (예외 전파 없음)
        """
        data = await self._get_json(
            SEARCH_URL,
            params={"q": query, "sort": "stars", "order": "desc", "per_page": per_page},
        )
        if not data:
            return []
        hits: list[RepoHit] = []
        for item in data.get("items", []):
            if item.get("archived") or item.get("fork"):
                continue
            hits.append(
                RepoHit(
                    full_name=item.get("full_name", ""),
                    html_url=item.get("html_url", ""),
                    description=item.get("description"),
                    stars=int(item.get("stargazers_count", 0)),
                    language=item.get("language"),
                    topics=list(item.get("topics") or []),
                    archived=bool(item.get("archived")),
                    fork=bool(item.get("fork")),
                    license=(item.get("license") or {}).get("spdx_id"),
                )
            )
        return hits

    async def fetch_readme(self, full_name: str) -> str:
        """README 앞부분(최대 3000자)을 반환. 없거나 실패하면 빈 문자열.

        입력: full_name — "owner/repo" 형식 저장소명
        출력: README 텍스트 앞 3000자 (실패·없음 시 "")
        결과: ?raw=1 우선, 실패 시 base64 Contents API로 폴백
        """
        url = CONTENTS_URL.format(full_name=full_name)
        try:
            # ?raw=1 은 raw.githubusercontent.com 으로 redirect 된다.
            resp = await self._client.get(
                url,
                params={"raw": "1"},
                headers=self._headers(),
                follow_redirects=True,
            )
            if resp.status_code == 200 and resp.text:
                return resp.text[:MAX_README_CHARS]
        except httpx.HTTPError:
            pass
        # fallback: JSON contents API (base64)
        data = await self._get_json(url)
        if not data:
            return ""
        content = data.get("content") or ""
        try:
            text = base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception:
            return ""
        return text[:MAX_README_CHARS]


def stars_delta(current: int, previous: int | None) -> int | None:
    """직전 스냅샷 대비 증가 star 수. 이전 데이터가 없으면 None.

    입력: current — 현재 star 수; previous — 직전 스냅샷 star 수 또는 None
    출력: 증가분(음수면 0), previous가 None이면 None
    결과: 없음 (순수 함수)
    """
    if previous is None:
        return None
    return max(0, current - previous)


def today_kst() -> str:
    """Asia/Seoul 기준 오늘 날짜 문자열.

    입력: 없음
    출력: "YYYY-MM-DD" 형식 날짜 문자열
    결과: 없음 (순수 함수)
    """
    return datetime.now(KST).date().isoformat()
