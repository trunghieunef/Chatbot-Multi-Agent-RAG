import pytest

from data_pipeline.embed import GeminiEmbedder


class FakeEmbedding:
    def __init__(self, values):
        self.values = values


class FakeResult:
    def __init__(self, values):
        self.embeddings = [FakeEmbedding(row) for row in values]


class FakeModels:
    def __init__(self):
        self.calls = []

    def embed_content(self, model, contents):
        self.calls.append((model, contents))
        return FakeResult([[float(i)] * 768 for i, _ in enumerate(contents, start=1)])


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


@pytest.mark.asyncio
async def test_embed_texts_batches_and_returns_vectors():
    client = FakeClient()
    embedder = GeminiEmbedder(api_key="test", client=client, batch_size=2)

    vectors = await embedder.embed_texts(["a", "b", "c"])

    assert len(vectors) == 3
    assert len(vectors[0]) == 768
    assert client.models.calls == [
        ("models/text-embedding-004", ["a", "b"]),
        ("models/text-embedding-004", ["c"]),
    ]


@pytest.mark.asyncio
async def test_embed_texts_returns_empty_for_empty_input():
    embedder = GeminiEmbedder(api_key="test", client=FakeClient())

    assert await embedder.embed_texts([]) == []
