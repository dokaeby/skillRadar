"""JSON 값 캐시. Redis 미설정/연결 실패 시 항상 miss하는 NullCache로 폴백한다."""

import json
import logging
from typing import Any

from backend.config import Settings

logger = logging.getLogger(__name__)


class JsonCache:
    """async get/set JSON 캐시 인터페이스."""

    async def get(self, key: str) -> Any | None:
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        return None

    async def aclose(self) -> None:
        return None


class NullCache(JsonCache):
    """항상 miss. Redis가 없거나 죽어도 수집 파이프라인을 막지 않는다."""


class RedisJsonCache(JsonCache):
    """redis.asyncio 위의 JSON 캐시. 연결은 첫 사용 시 lazy하게 맺는다."""

    def __init__(self, redis_url: str, client: Any | None = None) -> None:
        self._url = redis_url
        self._client = client  # 테스트 주입용; None이면 from_url로 lazy 생성

    async def _redis(self) -> Any:
        if self._client is None:
            from redis.asyncio import from_url

            self._client = from_url(self._url, decode_responses=True)
        return self._client

    async def get(self, key: str) -> Any | None:
        try:
            raw = await (await self._redis()).get(key)
        except Exception as exc:  # noqa: BLE001 - 캐시 장애가 수집을 막으면 안 됨
            logger.warning("Redis 캐시 get 실패, miss 처리: %s", exc)
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Redis 캐시 값 JSON 파싱 실패: %s", key)
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        try:
            await (await self._redis()).set(
                key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds
            )
        except Exception as exc:  # noqa: BLE001 - 캐시 쓰기 실패는 무시
            logger.warning("Redis 캐시 set 실패, 무시: %s", exc)

    async def aclose(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            try:
                await client.aclose()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis 캐시 종료 실패: %s", exc)


def get_cache(settings: Settings) -> JsonCache:
    """설정에 따라 RedisJsonCache 또는 NullCache를 반환한다."""
    if not settings.redis_enabled:
        return NullCache()
    return RedisJsonCache(settings.redis_url)
