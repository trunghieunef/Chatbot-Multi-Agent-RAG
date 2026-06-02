import pytest

from app.services.rag.hybrid_search import build_listing_filter_clauses, cohere_rerank


def test_build_listing_filter_clauses_maps_supported_filters():
    clauses, params = build_listing_filter_clauses(
        {
            "price_min": 3,
            "price_max": 5,
            "district": "Quận 7",
            "bedrooms": 2,
            "listing_type": "sale",
        }
    )

    sql = " ".join(clauses)

    assert "price >= :price_min" in sql
    assert "price <= :price_max" in sql
    assert "district ILIKE :district" in sql
    assert "bedrooms = :bedrooms" in sql
    assert "listing_type = :listing_type" in sql
    assert params["district"] == "%Quận 7%"


def test_build_listing_filter_clauses_always_filters_active_listings():
    clauses, _ = build_listing_filter_clauses({})
    assert clauses == ["is_active = true"]


def test_build_listing_filter_clauses_accepts_chatbot_price_aliases():
    clauses, params = build_listing_filter_clauses({"min_price": 2, "max_price": 5})

    sql = " ".join(clauses)

    assert "price >= :price_min" in sql
    assert "price <= :price_max" in sql
    assert params["price_min"] == 2
    assert params["price_max"] == 5


def test_build_listing_filter_clauses_accepts_chatbot_area_aliases():
    clauses, params = build_listing_filter_clauses({"min_area": 60, "max_area": 90})

    sql = " ".join(clauses)

    assert "area >= :area_min" in sql
    assert "area <= :area_max" in sql
    assert params["area_min"] == 60
    assert params["area_max"] == 90


@pytest.mark.asyncio
async def test_cohere_rerank_returns_truncated_input_when_api_key_missing(monkeypatch):
    from app import config as app_config

    monkeypatch.setattr(
        app_config,
        "get_settings",
        lambda: type("S", (), {"COHERE_API_KEY": "", "RERANK_MODEL": "x"})(),
    )

    chunks = [
        {"text": "a", "parent_id": 1, "chunk_type": "overview", "distance": 0.1},
        {"text": "b", "parent_id": 2, "chunk_type": "overview", "distance": 0.2},
        {"text": "c", "parent_id": 3, "chunk_type": "overview", "distance": 0.3},
    ]

    result = await cohere_rerank("query", chunks, top_n=2)

    assert result == chunks[:2]


@pytest.mark.asyncio
async def test_cohere_rerank_attaches_score_when_api_succeeds(monkeypatch):
    from app import config as app_config
    from app.services.rag import hybrid_search as hs

    fake_settings = type(
        "S",
        (),
        {"COHERE_API_KEY": "test-key", "RERANK_MODEL": "rerank-multilingual-v3.0"},
    )()
    monkeypatch.setattr(app_config, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(hs, "get_settings", lambda: fake_settings)

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *_, **__):
            return FakeResponse(
                {"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.4}]}
            )

    monkeypatch.setattr(hs.httpx, "AsyncClient", FakeAsyncClient)

    chunks = [
        {"text": "a", "parent_id": 1, "chunk_type": "overview", "distance": 0.1},
        {"text": "b", "parent_id": 2, "chunk_type": "overview", "distance": 0.2},
    ]

    result = await cohere_rerank("query", chunks, top_n=2)

    assert [chunk["parent_id"] for chunk in result] == [2, 1]
    assert result[0]["rerank_score"] == 0.9
    assert result[1]["rerank_score"] == 0.4


@pytest.mark.asyncio
async def test_cohere_rerank_cache_key_preserves_candidate_order(monkeypatch):
    from app import config as app_config
    from app.services.rag import hybrid_search as hs

    fake_settings = type("S", (), {"COHERE_API_KEY": "test-key", "RERANK_MODEL": "rerank-model"})()
    monkeypatch.setattr(app_config, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(hs, "get_settings", lambda: fake_settings)

    class FakeRedis:
        def __init__(self):
            self.store = {}

        async def get(self, key):
            return self.store.get(key)

        async def set(self, key, value, ex=None):
            self.store[key] = value

    redis = FakeRedis()

    async def fake_redis():
        return redis

    monkeypatch.setattr(hs, "get_redis_client", fake_redis)

    payloads = [
        {"results": [{"index": 0, "relevance_score": 0.9}]},
        {"results": [{"index": 0, "relevance_score": 0.7}]},
    ]

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *_, **__):
            return FakeResponse(payloads.pop(0))

    monkeypatch.setattr(hs.httpx, "AsyncClient", FakeAsyncClient)

    first = [
        {"id": 1, "text": "a", "parent_id": 1, "chunk_type": "overview", "distance": 0.1},
        {"id": 2, "text": "b", "parent_id": 2, "chunk_type": "overview", "distance": 0.2},
    ]
    second = [
        {"id": 2, "text": "b", "parent_id": 2, "chunk_type": "overview", "distance": 0.2},
        {"id": 1, "text": "a", "parent_id": 1, "chunk_type": "overview", "distance": 0.1},
    ]

    first_result = await cohere_rerank("query", first, top_n=1)
    second_result = await cohere_rerank("query", second, top_n=1)

    assert first_result[0]["parent_id"] == 1
    assert first_result[0]["rerank_score"] == 0.9
    assert second_result[0]["parent_id"] == 2
    assert second_result[0]["rerank_score"] == 0.7


@pytest.mark.asyncio
async def test_cohere_rerank_falls_back_on_http_error(monkeypatch):
    import httpx

    from app import config as app_config
    from app.services.rag import hybrid_search as hs

    fake_settings = type(
        "S",
        (),
        {"COHERE_API_KEY": "test-key", "RERANK_MODEL": "rerank-multilingual-v3.0"},
    )()
    monkeypatch.setattr(app_config, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(hs, "get_settings", lambda: fake_settings)

    class FlakyAsyncClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *_, **__):
            raise httpx.ConnectTimeout("cohere unreachable")

    monkeypatch.setattr(hs.httpx, "AsyncClient", FlakyAsyncClient)

    chunks = [
        {"text": "a", "parent_id": 1, "chunk_type": "overview", "distance": 0.1},
        {"text": "b", "parent_id": 2, "chunk_type": "overview", "distance": 0.2},
        {"text": "c", "parent_id": 3, "chunk_type": "overview", "distance": 0.3},
    ]

    result = await cohere_rerank("query", chunks, top_n=2)

    assert result == chunks[:2]
