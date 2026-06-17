import os

import pytest
from types import SimpleNamespace

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


def test_embedder_can_require_local_model_files(monkeypatch):
    calls = []

    class FakeSentenceTransformer:
        def __init__(self, model_name, **kwargs):
            calls.append((model_name, kwargs))
            self.max_seq_length = None

    monkeypatch.setitem(
        __import__("sys").modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    embedder = BGEEmbedder(
        model_name="BAAI/bge-m3",
        device="cpu",
        local_files_only=True,
    )

    assert isinstance(embedder.model, FakeSentenceTransformer)
    assert calls == [
        ("BAAI/bge-m3", {"device": "cpu", "local_files_only": True})
    ]


def test_embedder_uses_offline_env_when_local_only_kwarg_is_unsupported(monkeypatch):
    seen_env = {}

    class LegacySentenceTransformer:
        def __init__(self, model_name, device=None):
            seen_env["model_name"] = model_name
            seen_env["device"] = device
            seen_env["HF_HUB_OFFLINE"] = os.environ.get("HF_HUB_OFFLINE")
            seen_env["TRANSFORMERS_OFFLINE"] = os.environ.get("TRANSFORMERS_OFFLINE")
            self.max_seq_length = None

    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    monkeypatch.setitem(
        __import__("sys").modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=LegacySentenceTransformer),
    )

    embedder = BGEEmbedder(
        model_name="BAAI/bge-m3",
        device="cpu",
        local_files_only=True,
    )

    assert isinstance(embedder.model, LegacySentenceTransformer)
    assert seen_env == {
        "model_name": "BAAI/bge-m3",
        "device": "cpu",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    assert os.environ.get("HF_HUB_OFFLINE") is None
    assert os.environ.get("TRANSFORMERS_OFFLINE") is None
