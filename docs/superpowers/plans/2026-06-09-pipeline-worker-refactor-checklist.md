# Pipeline Worker Refactor Checklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Subagent-driven development is not used for implementation because the current working tree has many uncommitted changes and this refactor has tightly coupled file moves that should be applied sequentially to avoid overwriting local work. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move pipeline orchestration out of Backend into a dedicated Pipeline Worker, make Airflow call Pipeline Worker, and keep Backend/Agent Service as read/query runtimes.

**Architecture:** Backend remains public API and chat gateway. Agent Service remains multi-agent chatbot runtime. Pipeline Worker owns crawler/data_pipeline orchestration, chunking, embedding, legal ingestion, listing expiry, and old chunk cleanup. Airflow remains a lightweight scheduler that calls Pipeline Worker over internal HTTP.

**Tech Stack:** FastAPI, Docker Compose, Airflow 2.10.3, PostgreSQL/pgvector, existing `crawler` modules, existing `data_pipeline` ingestors, BGE-M3 via existing embedding wrapper.

---

### Task 1: Create Pipeline Worker Package

**Files:**
- Create: `pipeline_worker/__init__.py`
- Create: `pipeline_worker/security.py`
- Create: `pipeline_worker/runner.py`
- Create: `pipeline_worker/maintenance.py`
- Create: `pipeline_worker/main.py`
- Test: `backend/tests/test_pipeline_worker.py`

**Mục tiêu:** Move orchestration logic currently in `backend/app/routers/internal_pipeline.py` into a standalone Pipeline Worker package without duplicating crawler/data_pipeline logic.

- [x] Write tests for module command building, result parsing, internal-key protection, and health endpoint.
- [x] Run: `python -m pytest backend\tests\test_pipeline_worker.py -q`
- [x] Expected result before implementation: test fails because `pipeline_worker` does not exist.
- [x] Implement `pipeline_worker` package using existing subprocess pattern:
  - `python -m crawler...`
  - `python -m data_pipeline.ingestors...`
  - maintenance SQL for expired listings and old listing chunks.
- [x] Run: `python -m pytest backend\tests\test_pipeline_worker.py -q`
- [x] Expected result after implementation: all tests pass.

---

### Task 2: Remove Pipeline Orchestration From Backend

**Files:**
- Modify: `backend/app/main.py`
- Delete or leave unreferenced then remove: `backend/app/routers/internal_pipeline.py`
- Delete/replace: `backend/tests/test_internal_pipeline_router.py`

**Mục tiêu:** Backend must not expose `/internal/pipeline/*` and must not run crawler/chunk/ingest orchestration.

- [x] Remove `internal_pipeline` import from `backend/app/main.py`.
- [x] Remove `app.include_router(internal_pipeline.router)`.
- [x] Remove backend internal pipeline router file once Pipeline Worker tests cover equivalent behavior.
- [x] Remove old backend router test.
- [x] Run: `python -m compileall backend\app`
- [x] Expected result: compile succeeds.
- [x] Run: `rg -n "internal_pipeline|/internal/pipeline|Internal Pipeline" backend\app -S`
- [x] Expected result: no backend app/router references remain.

---

### Task 3: Make Airflow Call Pipeline Worker

**Files:**
- Modify: `airflow/plugins/pipeline_runner.py`
- Modify: `airflow/docker-compose.airflow.yml`
- Modify: `backend/tests/test_pipeline_runner.py`

**Mục tiêu:** Airflow should call `http://pipeline-worker:8200/internal/pipeline/*`, not Backend. Airflow must stay lightweight and must not install BGE-M3, Playwright, SQLAlchemy 2, pgvector, or pipeline dependencies.

- [x] Update runner env names:
  - `PIPELINE_WORKER_URL`
  - `PIPELINE_WORKER_DATA_ROOT`
- [x] Keep `/opt/project/data/...` to `/app/data/...` translation.
- [x] Update tests to expect `http://pipeline-worker:8200`.
- [x] Run: `python -m pytest backend\tests\test_pipeline_runner.py -q`
- [x] Expected result: all Airflow runner tests pass.
- [x] Run: `rg -n "SentenceTransformer|HF_EMBEDDING_MODEL|playwright|pgvector|sqlalchemy\[asyncio\]|PIPELINE_BACKEND_URL" airflow -S`
- [x] Expected result: no heavy pipeline dependency/model references in Airflow.

---

### Task 4: Add Pipeline Worker Docker Runtime

**Files:**
- Create: `pipeline_worker/requirements.txt`
- Create: `pipeline_worker/Dockerfile`
- Modify: `docker-compose.yml`
- Add: `backend/tests/test_pipeline_worker_docker.py`

**Mục tiêu:** Docker Compose can run `pipeline-worker` as a first-class service. Backend no longer mounts `crawler` or `data_pipeline`; Pipeline Worker owns those modules.

- [x] Add `pipeline-worker` service to `docker-compose.yml`.
- [x] Set environment:
  - `DATABASE_URL`
  - `REDIS_URL`
  - `AGENT_INTERNAL_KEY`
  - `GEMINI_API_KEY`
  - `INTENT_EXTRACTOR`
  - `CHATBOT_EMBEDDING_LOCAL_FILES_ONLY`
- [x] Mount `./data:/app/data`.
- [x] Add healthcheck for `http://localhost:8200/internal/pipeline/health`.
- [x] Remove backend mounts:
  - `./crawler:/app/crawler:ro`
  - `./data_pipeline:/app/data_pipeline:ro`
- [x] Remove Playwright/crawler deps from `backend/Dockerfile`.
- [x] Add compose/Dockerfile tests.
- [x] Run: `python -m pytest backend\tests\test_pipeline_worker_docker.py -q`
- [x] Expected result: tests pass and assert Pipeline Worker exists while Backend does not own crawler/data_pipeline mounts.

---

### Task 5: Keep Agent Service and Hybrid Search Boundaries

**Files:**
- Verify only: `agent_service/main.py`
- Verify only: `agent_service/tools/retrieval.py`
- Verify or modify minimally: `backend/app/services/rag/hybrid_search.py`
- Test: `backend/tests/test_hybrid_search.py`

**Mục tiêu:** Agent Service does not crawl/chunk/ingest. Retrieval keeps active/non-expired guard for listings.

- [x] Run: `rg -n "crawler|data_pipeline|ingest|playwright|/internal/pipeline" agent_service -S`
- [x] Expected result: no crawler/ingest orchestration references.
- [x] Confirm `hybrid_search.build_listing_filter_clauses()` includes:
  - `is_active = true`
  - `expiry_date` guard against expired listings.
- [x] Run: `python -m pytest backend\tests\test_hybrid_search.py -q`
- [x] Expected result: tests pass.

---

### Task 6: Full Local Verification

**Files:**
- No source changes.

**Mục tiêu:** Verify Python-level integration before Docker build.

- [x] Run: `python -m compileall pipeline_worker airflow\plugins airflow\dags backend\app agent_service`
- [x] Expected result: compile succeeds.
- [x] Run: `python -m pytest backend\tests\test_pipeline_runner.py backend\tests\test_pipeline_worker.py backend\tests\test_pipeline_worker_docker.py backend\tests\test_hybrid_search.py -q`
- [x] Expected result: all selected tests pass.

---

### Task 7: Docker Compose Commands To Run Manually

**Files:**
- No source changes.

**Mục tiêu:** Provide exact commands to run the full stack after code-level verification.

- [ ] Build/start core stack:

```powershell
docker compose up -d --build postgres redis pipeline-worker backend agent-service frontend
```

- [ ] Start Airflow:

```powershell
docker compose -f airflow\docker-compose.airflow.yml up -d --build
```

- [ ] Health checks:

```powershell
curl.exe -H "X-Internal-Agent-Key: local-agent-internal-key-realestate-v2-2026" http://localhost:8200/internal/pipeline/health
curl.exe http://localhost:8000/api/v1/health
```

- [ ] Expected result:
  - Pipeline Worker health returns `{"status":"ok","service":"pipeline-worker"}`.
  - Backend health returns `{"status":"ok","version":"2.0.0"}`.
  - Airflow UI opens at `http://localhost:8080`.

---

## Notes

- Do not rewrite `crawler/` or `data_pipeline/`.
- Do not add BGE-M3, Playwright, SQLAlchemy 2, pgvector, or embedding logic into Airflow.
- Do not add crawl/chunk/ingest endpoints to Agent Service.
- Do not change DB schema unless a test proves it is required.
- Do not revert unrelated dirty working tree files.
