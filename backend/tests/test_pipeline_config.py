from app.config import Settings


def test_pipeline_defaults_use_m1_embedding_model(monkeypatch):
    for var in (
        "GEMINI_EMBEDDING_MODEL",
        "EMBEDDING_DIM",
        "CHUNK_SIZE_TOKENS",
        "CHUNK_OVERLAP_TOKENS",
        "RERANK_PROVIDER",
        "RERANK_MODEL",
        "RERANK_TOP_N",
        "COHERE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)

    assert settings.GEMINI_EMBEDDING_MODEL == "models/text-embedding-004"
    assert settings.EMBEDDING_DIM == 768
    assert settings.CHUNK_SIZE_TOKENS == 400
    assert settings.RERANK_PROVIDER == "cohere"
    assert settings.RERANK_TOP_N == 5
