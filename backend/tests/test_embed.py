import pytest

from data_pipeline.embed import BGEEmbedder


class FakeBGEModel:
    def __init__(self):
        self.calls = []
        self.max_seq_length = None

    def encode(self, texts, **kwargs):
        self.calls.append((list(texts), kwargs))
        return [[float(i)] * 1024 for i, _ in enumerate(texts, start=1)]


@pytest.mark.asyncio
async def test_embed_texts_batches_and_returns_vectors():
    model = FakeBGEModel()
    embedder = BGEEmbedder(model=model, batch_size=2)

    vectors = await embedder.embed_texts(["a", "b", "c"])

    assert len(vectors) == 3
    assert len(vectors[0]) == 1024
    assert model.calls == [
        (["a", "b"], {"normalize_embeddings": True, "show_progress_bar": False}),
        (["c"], {"normalize_embeddings": True, "show_progress_bar": False}),
    ]


@pytest.mark.asyncio
async def test_embed_texts_returns_empty_for_empty_input():
    embedder = BGEEmbedder(model=FakeBGEModel())

    assert await embedder.embed_texts([]) == []
