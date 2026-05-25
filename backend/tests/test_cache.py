import pytest

from chatbot.tools.cache import JsonCache


class FakeRedis:
    def __init__(self):
        self.store: dict[str, tuple[str, int | None]] = {}

    async def get(self, key: str):
        record = self.store.get(key)
        return record[0] if record else None

    async def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = (value, ex)


@pytest.mark.asyncio
async def test_cache_get_returns_none_for_missing_key():
    cache = JsonCache(client=FakeRedis(), namespace="test")
    assert await cache.get("missing") is None


@pytest.mark.asyncio
async def test_cache_set_then_get_round_trips_payload():
    cache = JsonCache(client=FakeRedis(), namespace="test", ttl_seconds=60)

    await cache.set("k", {"foo": [1, 2, 3]})
    payload = await cache.get("k")

    assert payload == {"foo": [1, 2, 3]}


@pytest.mark.asyncio
async def test_cache_namespaces_keys_to_avoid_collision():
    redis = FakeRedis()
    a = JsonCache(client=redis, namespace="a")
    b = JsonCache(client=redis, namespace="b")

    await a.set("same", 1)
    await b.set("same", 2)

    assert await a.get("same") == 1
    assert await b.get("same") == 2
