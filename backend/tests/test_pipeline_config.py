from app.config import Settings


def test_pipeline_defaults_use_m1_embedding_model():
    settings = Settings()

    assert settings.GEMINI_EMBEDDING_MODEL == "models/text-embedding-004"
    assert settings.EMBEDDING_DIM == 768
    assert settings.CHUNK_SIZE_TOKENS == 400
    assert settings.RERANK_PROVIDER == "cohere"
    assert settings.RERANK_TOP_N == 5
