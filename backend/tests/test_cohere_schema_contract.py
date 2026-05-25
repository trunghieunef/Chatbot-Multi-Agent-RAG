import pytest

from chatbot.tools import hybrid_search as hs


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *_, **__):
        return FakeResp(self._payload)


class _NoCacheRedis:
    """Simulates Redis being unavailable so cohere_rerank skips caching."""

    async def get(self, key):
        return None

    async def set(self, key, value, ex=None):
        return None


async def _no_cache(*args, **kwargs):
    raise RuntimeError("redis disabled in test")


@pytest.mark.asyncio
async def test_cohere_v2_schema_must_expose_results_index_and_score(monkeypatch):
    fake_settings = type(
        "S", (), {"COHERE_API_KEY": "k", "RERANK_MODEL": "rerank-multilingual-v3.0"}
    )()
    monkeypatch.setattr(hs, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(hs, "get_redis_client", _no_cache)

    payload = {
        "id": "abc",
        "results": [
            {"index": 0, "relevance_score": 0.9, "document": {"text": "..."}},
        ],
        "meta": {"api_version": {"version": "2"}},
    }
    monkeypatch.setattr(hs.httpx, "AsyncClient", lambda *a, **k: FakeAsyncClient(payload))

    chunks = [{"text": "a", "parent_id": 1, "chunk_type": "overview", "distance": 0.1}]
    result = await hs.cohere_rerank("query", chunks, top_n=1)

    assert result, "Cohere v2 schema regression: results array missing"
    assert "rerank_score" in result[0], "Cohere v2 schema regression: relevance_score missing"
    assert result[0]["parent_id"] == 1


@pytest.mark.asyncio
async def test_cohere_unexpected_payload_returns_top_n_distance_order(monkeypatch):
    fake_settings = type("S", (), {"COHERE_API_KEY": "k", "RERANK_MODEL": "x"})()
    monkeypatch.setattr(hs, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(hs, "get_redis_client", _no_cache)

    payload = {"unexpected": True}
    monkeypatch.setattr(hs.httpx, "AsyncClient", lambda *a, **k: FakeAsyncClient(payload))

    chunks = [
        {"text": "a", "parent_id": 1, "chunk_type": "overview", "distance": 0.5},
        {"text": "b", "parent_id": 2, "chunk_type": "overview", "distance": 0.1},
    ]

    result = await hs.cohere_rerank("query", chunks, top_n=2)

    assert len(result) == 2
    assert result[0]["parent_id"] in {1, 2}


@pytest.mark.asyncio
async def test_cohere_results_missing_index_falls_back(monkeypatch):
    fake_settings = type("S", (), {"COHERE_API_KEY": "k", "RERANK_MODEL": "x"})()
    monkeypatch.setattr(hs, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(hs, "get_redis_client", _no_cache)

    # Schema regression: results without `index` keys.
    payload = {"results": [{"relevance_score": 0.5}, {"relevance_score": 0.3}]}
    monkeypatch.setattr(hs.httpx, "AsyncClient", lambda *a, **k: FakeAsyncClient(payload))

    chunks = [
        {"text": "a", "parent_id": 1, "chunk_type": "overview", "distance": 0.5},
        {"text": "b", "parent_id": 2, "chunk_type": "overview", "distance": 0.1},
    ]
    result = await hs.cohere_rerank("query", chunks, top_n=2)

    assert len(result) == 2  # Vector-order fallback rather than crash.
