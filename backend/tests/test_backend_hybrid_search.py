import pytest

from app.services.rag import hybrid_search as hs


class StubCache:
    def __init__(self, payload):
        self.payload = payload
        self.get_calls = []
        self.set_calls = []

    async def get(self, key):
        self.get_calls.append(key)
        return self.payload

    async def set(self, key, value):
        self.set_calls.append((key, value))


class StubEmbedder:
    provider = "bge_m3"
    model_name = "BAAI/bge-m3"
    embedding_dim = 1024

    def __init__(self):
        self.calls = 0

    async def embed_texts(self, texts):
        self.calls += 1
        return [[0.5] * 1024 for _ in texts]


def test_embedding_cache_namespace_includes_bge_model_and_dimension():
    embedder = StubEmbedder()

    namespace = hs.embedding_cache_namespace(embedder)

    assert namespace == "bge_m3:BAAI/bge-m3:1024"


@pytest.mark.asyncio
async def test_get_query_embedding_uses_bge_cache_namespace_on_miss():
    cache = StubCache(payload=None)
    embedder = StubEmbedder()

    vector = await hs.get_query_embedding("căn hộ Quận 7", embedder=embedder, cache=cache)

    assert len(vector) == 1024
    assert embedder.calls == 1
    assert cache.get_calls
    assert cache.set_calls
