"""storage.cache 테스트. 외부 의존성 없이 fake redis 클라이언트를 주입한다."""

import json

from backend.config import Settings
from backend.storage.cache import JsonCache, NullCache, RedisJsonCache, get_cache


class FakeRedis:
    """redis.asyncio 클라이언트 흉내. get/set만 구현."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.closed = False

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def aclose(self) -> None:
        self.closed = True


async def test_null_cache_always_misses() -> None:
    cache = NullCache()
    assert await cache.get("anything") is None
    await cache.set("anything", {"a": 1}, ttl_seconds=60)  # no-op, 예외 없어야 함
    assert await cache.get("anything") is None
    await cache.aclose()


async def test_get_cache_returns_null_when_redis_disabled() -> None:
    settings = Settings(redis_url="")
    assert isinstance(get_cache(settings), NullCache)


def test_get_cache_returns_redis_when_enabled() -> None:
    settings = Settings(redis_url="redis://localhost:6379/0")
    cache = get_cache(settings)
    assert isinstance(cache, RedisJsonCache)


async def test_redis_cache_roundtrip_json() -> None:
    fake = FakeRedis()
    cache = RedisJsonCache("redis://fake", client=fake)
    await cache.set("k1", {"label": "agents", "n": 3}, ttl_seconds=60)
    assert json.loads(fake.store["k1"]) == {"label": "agents", "n": 3}
    assert await cache.get("k1") == {"label": "agents", "n": 3}
    assert await cache.get("missing") is None
    await cache.aclose()
    assert fake.closed


async def test_redis_cache_corrupt_value_returns_none() -> None:
    fake = FakeRedis()
    fake.store["bad"] = "{not json"
    cache = RedisJsonCache("redis://fake", client=fake)
    assert await cache.get("bad") is None


async def test_redis_cache_connection_error_degrades_to_miss() -> None:
    class BrokenRedis:
        async def get(self, key: str) -> str | None:
            raise ConnectionError("redis down")

        async def set(self, key: str, value: str, ex: int | None = None) -> None:
            raise ConnectionError("redis down")

    cache = RedisJsonCache("redis://fake", client=BrokenRedis())
    assert await cache.get("k") is None  # miss, 예외 전파 없음
    await cache.set("k", {"x": 1}, ttl_seconds=10)  # no-op, 예외 전파 없음


async def test_json_cache_interface_defaults() -> None:
    cache = JsonCache()
    assert await cache.get("k") is None
    await cache.set("k", 1, ttl_seconds=1)
    await cache.aclose()
