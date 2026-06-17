from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_compose_defines_pipeline_worker_service():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "  pipeline-worker:" in compose
    assert "dockerfile: pipeline_worker/Dockerfile" in compose
    assert "container_name: realestate_pipeline_worker" in compose
    assert "AGENT_INTERNAL_KEY: ${AGENT_INTERNAL_KEY}" in compose
    assert "DATABASE_URL: postgresql+asyncpg://" in compose
    assert "INTENT_EXTRACTOR: ${INTENT_EXTRACTOR:-rule}" in compose
    assert "CHATBOT_EMBEDDING_LOCAL_FILES_ONLY: ${CHATBOT_EMBEDDING_LOCAL_FILES_ONLY:-true}" in compose
    assert "http://localhost:8200/internal/pipeline/health" in compose


def test_backend_compose_service_does_not_mount_pipeline_sources():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    backend_block = compose.split("  backend:", maxsplit=1)[1].split("  agent-service:", maxsplit=1)[0]

    assert "./crawler:/app/crawler" not in backend_block
    assert "./data_pipeline:/app/data_pipeline" not in backend_block


def test_backend_dockerfile_does_not_install_playwright():
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

    assert "playwright install" not in dockerfile
    assert "playwright-stealth" not in dockerfile
    assert "HF_EMBEDDING_MODEL" not in dockerfile
    assert "SentenceTransformer" not in dockerfile


def test_backend_requirements_do_not_include_pipeline_or_embedding_runtime():
    requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")

    assert "sentence-transformers" not in requirements
    assert "datasets" not in requirements
    assert "pyarrow" not in requirements
    assert "pymupdf" not in requirements
    assert "beautifulsoup4" not in requirements
    assert "google-genai" not in requirements
    assert "aiosqlite" not in requirements
    assert "pytest-asyncio" not in requirements


def test_pipeline_worker_dockerfile_owns_heavy_pipeline_runtime():
    dockerfile = (ROOT / "pipeline_worker" / "Dockerfile").read_text(encoding="utf-8")

    assert "python -m playwright install" in dockerfile
    assert "SentenceTransformer" in dockerfile
    assert "COPY crawler ./crawler" in dockerfile
    assert "COPY data_pipeline ./data_pipeline" in dockerfile
