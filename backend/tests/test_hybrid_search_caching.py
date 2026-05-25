import pytest

from chatbot.tools import hybrid_search as hs


class StubCache:
    def __init__(self, payload):
        self.payload = payload
        self.set_calls = []

    async def get(self, key):
        return self.payload

    async def set(self, key, value):
        self.set_calls.append((key, value))


class StubEmbedder:
    def __init__(self):
        self.calls = 0
        self.model = "stub-model"

    async def embed_texts(self, texts):
        self.calls += 1
        return [[0.5] * 768 for _ in texts]


@pytest.mark.asyncio
async def test_get_query_embedding_uses_cache_when_available():
    cache = StubCache(payload=[0.1] * 768)
    embedder = StubEmbedder()

    vector = await hs.get_query_embedding("căn hộ Quận 7", embedder=embedder, cache=cache)

    assert vector == [0.1] * 768
    assert embedder.calls == 0


@pytest.mark.asyncio
async def test_get_query_embedding_populates_cache_on_miss():
    cache = StubCache(payload=None)
    embedder = StubEmbedder()

    vector = await hs.get_query_embedding("căn hộ Quận 7", embedder=embedder, cache=cache)

    assert len(vector) == 768
    assert embedder.calls == 1
    assert len(cache.set_calls) == 1


@pytest.mark.asyncio
async def test_get_query_embedding_works_without_cache():
    embedder = StubEmbedder()

    vector = await hs.get_query_embedding("căn hộ Quận 7", embedder=embedder, cache=None)

    assert len(vector) == 768
    assert embedder.calls == 1
