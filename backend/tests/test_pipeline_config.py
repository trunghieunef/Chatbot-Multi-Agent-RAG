from app.config import Settings


def test_pipeline_defaults_use_bge_m3_embedding_model(monkeypatch):
    for var in (
        "EMBEDDING_PROVIDER",
        "GEMINI_EMBEDDING_MODEL",
        "HF_EMBEDDING_MODEL",
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

    assert settings.EMBEDDING_PROVIDER == "bge_m3"
    assert settings.HF_EMBEDDING_MODEL == "BAAI/bge-m3"
    assert settings.GEMINI_EMBEDDING_MODEL == "gemini-embedding-001"
    assert settings.EMBEDDING_DIM == 1024
    assert settings.CHUNK_SIZE_TOKENS == 400
    assert settings.RERANK_PROVIDER == "cohere"
    assert settings.RERANK_TOP_N == 5
