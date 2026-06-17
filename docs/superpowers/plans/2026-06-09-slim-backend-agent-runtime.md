# Slim Backend Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Backend use Agent Service by default and remove BGE-M3/pipeline-only dependencies from the Backend Docker runtime while keeping Agent Service retrieval functional.

**Architecture:** Backend remains a public API and chat gateway. Agent Service owns chatbot retrieval/query embedding, so it keeps BGE-M3. Pipeline Worker owns chunk embedding and crawler/data_pipeline dependencies, so Backend must not preload BGE-M3 or carry legal/crawler/pipeline-only packages.

**Tech Stack:** FastAPI, Docker Compose, Python requirements, pytest, BGE-M3 via `sentence-transformers` in Agent Service and Pipeline Worker only.

---

### Task 1: Encode New Defaults In Tests

**Files:**
- Modify: `backend/tests/test_agent_service_client.py`
- Modify: `backend/tests/test_agent_service_docker_config.py`
- Modify: `backend/tests/test_pipeline_worker_docker.py`

**Mục tiêu:** Tests must assert Backend defaults to Agent Service and Backend Docker runtime does not preload BGE-M3 or install pipeline-only dependencies.

- [x] Change `test_agent_service_settings_defaults` expected value to `settings.CHATBOT_AGENT_SERVICE_ENABLED is True`.
- [x] Change compose test expected string to `CHATBOT_AGENT_SERVICE_ENABLED: ${CHATBOT_AGENT_SERVICE_ENABLED:-true}`.
- [x] Change `.env.example` test expected string to `CHATBOT_AGENT_SERVICE_ENABLED=true`.
- [x] Add assertions that `backend/Dockerfile` does not contain `HF_EMBEDDING_MODEL` or `SentenceTransformer`.
- [x] Add assertions that `backend/requirements.txt` does not contain `sentence-transformers`, `datasets`, `pyarrow`, `pymupdf`, `beautifulsoup4`, `google-genai`, `aiosqlite`, or `pytest-asyncio`.
- [x] Run: `python -m pytest backend\tests\test_agent_service_client.py backend\tests\test_agent_service_docker_config.py backend\tests\test_pipeline_worker_docker.py -q`
- [x] Expected before implementation: tests fail on old defaults and Backend BGE/dependency references.

### Task 2: Slim Backend Runtime

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/Dockerfile`
- Modify: `backend/requirements.txt`
- Modify: `docker-compose.yml`
- Modify: `.env`
- Modify: `.env.example`

**Mục tiêu:** Backend image no longer downloads BGE-M3 or pipeline-only packages, and chat uses Agent Service by default.

- [x] Set `Settings.CHATBOT_AGENT_SERVICE_ENABLED` default to `True`.
- [x] Remove `ENV HF_EMBEDDING_MODEL=BAAI/bge-m3` from `backend/Dockerfile`.
- [x] Remove Backend Docker preload command `SentenceTransformer(...)`.
- [x] Remove these Backend runtime dependencies: `google-genai`, `sentence-transformers`, `datasets`, `pyarrow`, `pymupdf`, `beautifulsoup4`, `aiosqlite`, `pytest-asyncio`.
- [x] Keep Backend dependencies required for API/retrieval fallback code imports: FastAPI stack, SQLAlchemy/asyncpg/pgvector, auth, redis, `httpx`, `prometheus-client`.
- [x] Change `docker-compose.yml` Backend default to `CHATBOT_AGENT_SERVICE_ENABLED: ${CHATBOT_AGENT_SERVICE_ENABLED:-true}`.
- [x] Change `.env` and `.env.example` to `CHATBOT_AGENT_SERVICE_ENABLED=true`.
- [x] Run: `python -m pytest backend\tests\test_agent_service_client.py backend\tests\test_agent_service_docker_config.py backend\tests\test_pipeline_worker_docker.py -q`
- [x] Expected after implementation: tests pass.

### Task 3: Trim Agent Service Only Where Safe

**Files:**
- Modify: `agent_service/requirements.txt`

**Mục tiêu:** Keep BGE-M3 in Agent Service, remove only unused small dependency.

- [x] Remove `prometheus-client>=0.21` from `agent_service/requirements.txt` because no `agent_service` code imports it.
- [x] Keep `sentence-transformers`, `google-genai`, `langgraph`, `sqlalchemy[asyncio]`, `asyncpg`, `pgvector`, and `redis`.
- [x] Run: `python -m compileall agent_service`
- [x] Expected result: compile succeeds.

### Task 4: Full Verification

**Files:**
- No source changes.

**Mục tiêu:** Verify the slim runtime config and affected Python code.

- [x] Run: `python -m pytest backend\tests\test_agent_service_client.py backend\tests\test_agent_service_docker_config.py backend\tests\test_pipeline_worker_docker.py backend\tests\test_pipeline_runner.py -q`
- [x] Expected result: all selected tests pass.
- [x] Run: `python -m compileall backend\app agent_service pipeline_worker`
- [x] Expected result: compile succeeds.
- [x] Run: `docker compose config --services`
- [x] Expected result: compose parses and includes `backend`, `agent-service`, and `pipeline-worker`.
