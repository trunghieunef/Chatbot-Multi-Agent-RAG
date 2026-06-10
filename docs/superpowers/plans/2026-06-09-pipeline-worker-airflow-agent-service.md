# Pipeline Worker Airflow Agent Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split scheduled data processing into a dedicated Pipeline Worker so Airflow only schedules jobs, Pipeline Worker handles crawl/ingest/chunk/embedding/cleanup, Backend serves public APIs, and Agent Service handles chatbot reasoning.

**Architecture:** Airflow calls Pipeline Worker internal HTTP endpoints using `X-Internal-Agent-Key`. Pipeline Worker runs crawler and `data_pipeline` modules, writes parent tables and `chunks`, and performs listing expiry maintenance. Backend and Agent Service read PostgreSQL/pgvector only; they do not run scheduled crawl/chunk jobs.

**Tech Stack:** Docker Compose, FastAPI, Python subprocess, PostgreSQL/pgvector, BGE-M3 via `sentence-transformers`, Playwright crawlers, existing `data_pipeline` ingestors, Airflow 2.10.3.

---

## File Structure

- Create: `pipeline_worker/Dockerfile`
  Builds the runtime for crawler, ingestors, chunking, embedding, legal parser, and maintenance jobs.

- Create: `pipeline_worker/requirements.txt`
  Contains pipeline-only dependencies: crawler, DB, BGE-M3, legal parsing, and minimal FastAPI server dependencies.

- Create: `pipeline_worker/main.py`
  FastAPI internal service exposing `/internal/pipeline/*` endpoints.

- Create: `pipeline_worker/security.py`
  Validates `X-Internal-Agent-Key`.

- Create: `pipeline_worker/runner.py`
  Runs project modules with `python -m ...`, captures stdout/stderr, parses result dicts.

- Create: `pipeline_worker/maintenance.py`
  Deactivates expired listings and deletes old inactive listing chunks.

- Modify: `docker-compose.yml`
  Adds `pipeline-worker`, mounts `data`, `crawler`, `data_pipeline`, `backend/app`, and optionally shared HuggingFace cache.

- Modify: `airflow/docker-compose.airflow.yml`
  Points Airflow to `http://pipeline-worker:8200`; Airflow does not mount model cache and does not install pipeline dependencies.

- Modify: `airflow/plugins/pipeline_runner.py`
  Calls Pipeline Worker endpoints, not Backend.

- Modify: `airflow/dags/daily_listings_dag.py`
  Keeps DAG structure but calls Pipeline Worker for crawl, ingest, deactivate, and cleanup.

- Modify: `airflow/requirements.txt`
  Keeps Airflow light. Only Airflow provider packages needed by DAGs remain.

- Modify: `backend/app/main.py`
  Ensures Backend does not expose temporary `/internal/pipeline/*` orchestration endpoints.

- Modify: `backend/app/services/rag/hybrid_search.py`
  Keeps runtime guard that listing retrieval only returns active and non-expired listings.

- Test: `backend/tests/test_pipeline_runner.py`
  Verifies Airflow runner posts to Pipeline Worker and translates `/opt/project/data/...` to `/app/data/...`.

- Test: `backend/tests/test_pipeline_worker_runner.py`
  Verifies module command construction, result parsing, and subprocess error handling.

- Test: `backend/tests/test_pipeline_worker_security.py`
  Verifies internal key rejection.

- Test: `backend/tests/test_pipeline_worker_maintenance.py`
  Verifies SQL used for expiry and old chunk cleanup.

---

### Task 1: Add Pipeline Worker Security and Module Runner

**Files:**
- Create: `pipeline_worker/security.py`
- Create: `pipeline_worker/runner.py`
- Test: `backend/tests/test_pipeline_worker_runner.py`
- Test: `backend/tests/test_pipeline_worker_security.py`

- [ ] **Step 1: Write security tests**

Create `backend/tests/test_pipeline_worker_security.py`:

```python
import os

import pytest
from fastapi import HTTPException

from pipeline_worker.security import require_internal_key


def test_require_internal_key_accepts_matching_key(monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret")

    assert require_internal_key("secret") is None


def test_require_internal_key_rejects_missing_or_wrong_key(monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret")

    with pytest.raises(HTTPException) as exc:
        require_internal_key("wrong")

    assert exc.value.status_code == 403
```

- [ ] **Step 2: Write runner tests**

Create `backend/tests/test_pipeline_worker_runner.py`:

```python
import subprocess

import pytest
from fastapi import HTTPException

from pipeline_worker.runner import build_module_command, parse_result, run_module


def test_build_module_command_expands_flags_and_lists():
    cmd = build_module_command(
        "crawler.sale.crawl_urls",
        {"--pages": ["1", "2"], "--output": "/app/data/raw/sale_urls.csv", "--empty": ""},
    )

    assert cmd[1:] == [
        "-m",
        "crawler.sale.crawl_urls",
        "--pages",
        "1",
        "2",
        "--output",
        "/app/data/raw/sale_urls.csv",
    ]


def test_parse_result_accepts_python_dict_output():
    result = parse_result("{'published': 1, 'indexed': 1, 'chunks': 4}\n")

    assert result == {"published": 1, "indexed": 1, "chunks": 4}


def test_run_module_raises_http_exception_on_nonzero_exit(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=2, stdout="out", stderr="err")

    monkeypatch.setattr("pipeline_worker.runner.subprocess.run", fake_run)

    with pytest.raises(HTTPException) as exc:
        run_module("crawler.sale.crawl_urls", {})

    assert exc.value.status_code == 500
    assert exc.value.detail["returncode"] == 2
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
python -m pytest backend\tests\test_pipeline_worker_runner.py backend\tests\test_pipeline_worker_security.py -q
```

Expected:

```text
ERROR or FAIL because pipeline_worker package does not exist
```

- [ ] **Step 4: Implement security**

Create `pipeline_worker/security.py`:

```python
from __future__ import annotations

import os

from fastapi import HTTPException


def require_internal_key(x_internal_agent_key: str | None) -> None:
    expected = os.environ.get("AGENT_INTERNAL_KEY", "")
    if not expected or x_internal_agent_key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal key")
```

- [ ] **Step 5: Implement runner**

Create `pipeline_worker/runner.py`:

```python
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import HTTPException


PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", "/app")).resolve()


def build_module_command(module: str, args: dict[str, Any]) -> list[str]:
    cmd: list[str] = [sys.executable, "-m", module]
    for flag, value in args.items():
        if isinstance(value, list):
            cmd.append(flag)
            cmd.extend(str(item) for item in value)
        elif value is None or value == "":
            continue
        else:
            cmd.extend([flag, str(value)])
    return cmd


def run_module(module: str, args: dict[str, Any], timeout: int = 7200) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    project_paths = [str(PROJECT_ROOT), str(PROJECT_ROOT / "backend")]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        project_paths.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(project_paths)

    completed = subprocess.run(
        build_module_command(module, args),
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if completed.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "module": module,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        )
    return completed


def parse_result(stdout: str) -> dict[str, Any]:
    clean = stdout.strip()
    if not clean:
        return {}
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        parsed = ast.literal_eval(clean.splitlines()[-1])
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=500, detail=f"Pipeline result is not a dict: {parsed!r}")
    return parsed
```

- [ ] **Step 6: Run tests and verify GREEN**

Run:

```powershell
python -m pytest backend\tests\test_pipeline_worker_runner.py backend\tests\test_pipeline_worker_security.py -q
```

Expected:

```text
5 passed
```

---

### Task 2: Add Pipeline Worker Internal API

**Files:**
- Create: `pipeline_worker/main.py`
- Test: `backend/tests/test_pipeline_worker_api.py`

- [ ] **Step 1: Write API tests**

Create `backend/tests/test_pipeline_worker_api.py`:

```python
from fastapi.testclient import TestClient

from pipeline_worker.main import app


def test_health_requires_internal_key(monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret")
    client = TestClient(app)

    response = client.get("/internal/pipeline/health")

    assert response.status_code == 403


def test_health_accepts_internal_key(monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret")
    client = TestClient(app)

    response = client.get("/internal/pipeline/health", headers={"X-Internal-Agent-Key": "secret"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

- [ ] **Step 2: Run test and verify RED**

Run:

```powershell
python -m pytest backend\tests\test_pipeline_worker_api.py -q
```

Expected:

```text
ERROR because pipeline_worker.main does not exist
```

- [ ] **Step 3: Implement API**

Create `pipeline_worker/main.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header
from pydantic import BaseModel, Field

from pipeline_worker.runner import parse_result, run_module
from pipeline_worker.security import require_internal_key


app = FastAPI(title="Real Estate Pipeline Worker", version="0.1.0")


class CrawlerRequest(BaseModel):
    module: str
    args: dict[str, Any] = Field(default_factory=dict)
    timeout: int = 7200


class CsvIngestRequest(BaseModel):
    csv_path: str
    batch_size: int = 50


class CleanupChunksRequest(BaseModel):
    retention_days: int = 60


@app.get("/internal/pipeline/health")
def health(x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key")) -> dict:
    require_internal_key(x_internal_agent_key)
    return {"status": "ok", "service": "pipeline-worker"}


@app.post("/internal/pipeline/crawler")
def run_crawler(
    payload: CrawlerRequest,
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    completed = run_module(payload.module, payload.args, timeout=payload.timeout)
    return {"stdout": completed.stdout, "stderr": completed.stderr}


@app.post("/internal/pipeline/ingest/listings")
def ingest_listings(
    payload: CsvIngestRequest,
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    completed = run_module(
        "data_pipeline.ingestors.listings_ingestor",
        {"--csv": payload.csv_path, "--batch-size": str(payload.batch_size)},
    )
    return {"result": parse_result(completed.stdout), "stderr": completed.stderr}


@app.post("/internal/pipeline/ingest/projects")
def ingest_projects(
    payload: CsvIngestRequest,
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    completed = run_module(
        "data_pipeline.ingestors.projects_ingestor",
        {"--csv": payload.csv_path, "--batch-size": str(payload.batch_size)},
    )
    return {"result": parse_result(completed.stdout), "stderr": completed.stderr}


@app.post("/internal/pipeline/ingest/news")
def ingest_news(
    payload: CsvIngestRequest,
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    completed = run_module(
        "data_pipeline.ingestors.news_ingestor",
        {"--csv": payload.csv_path, "--batch-size": str(payload.batch_size)},
    )
    return {"result": parse_result(completed.stdout), "stderr": completed.stderr}


@app.post("/internal/pipeline/ingest/legal")
def ingest_legal(
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    completed = run_module("data_pipeline.ingestors.legal_kb_ingestor", {})
    return {"result": parse_result(completed.stdout), "stderr": completed.stderr}
```

- [ ] **Step 4: Run API tests and verify GREEN**

Run:

```powershell
python -m pytest backend\tests\test_pipeline_worker_api.py -q
```

Expected:

```text
2 passed
```

---

### Task 3: Add Maintenance Jobs to Pipeline Worker

**Files:**
- Create: `pipeline_worker/maintenance.py`
- Modify: `pipeline_worker/main.py`
- Test: `backend/tests/test_pipeline_worker_maintenance.py`

- [ ] **Step 1: Write maintenance tests**

Create `backend/tests/test_pipeline_worker_maintenance.py`:

```python
from pipeline_worker.maintenance import cleanup_expired_listing_chunks_sql, deactivate_expired_listings_sql


def test_deactivate_expired_listings_sql_filters_expiry_formats():
    sql = deactivate_expired_listings_sql()

    assert "UPDATE listings" in sql
    assert "is_active = false" in sql
    assert "DD/MM/YYYY" in sql
    assert "YYYY-MM-DD" in sql


def test_cleanup_expired_listing_chunks_sql_deletes_only_listing_chunks():
    sql = cleanup_expired_listing_chunks_sql()

    assert "DELETE FROM chunks" in sql
    assert "c.parent_type = 'listing'" in sql
    assert "retention_days" in sql
```

- [ ] **Step 2: Run test and verify RED**

Run:

```powershell
python -m pytest backend\tests\test_pipeline_worker_maintenance.py -q
```

Expected:

```text
ERROR because pipeline_worker.maintenance does not exist
```

- [ ] **Step 3: Implement maintenance module**

Create `pipeline_worker/maintenance.py`:

```python
from __future__ import annotations

from sqlalchemy import text

from app.database import async_session


def deactivate_expired_listings_sql() -> str:
    return """
        UPDATE listings
           SET is_active = false,
               updated_at = NOW()
         WHERE is_active = true
           AND expiry_date IS NOT NULL
           AND expiry_date <> ''
           AND (
                CASE WHEN expiry_date ~ '^\\d{2}/\\d{2}/\\d{4}$'
                     THEN to_date(expiry_date, 'DD/MM/YYYY') < CURRENT_DATE
                     WHEN expiry_date ~ '^\\d{4}-\\d{2}-\\d{2}$'
                     THEN to_date(expiry_date, 'YYYY-MM-DD') < CURRENT_DATE
                     ELSE false
                END
           )
    """


def cleanup_expired_listing_chunks_sql() -> str:
    return """
        DELETE FROM chunks c
         USING listings l
         WHERE c.parent_type = 'listing'
           AND c.parent_id = l.id
           AND l.is_active = false
           AND COALESCE(l.updated_at, l.created_at) < NOW() - (:retention_days * INTERVAL '1 day')
    """


async def deactivate_expired_listings() -> dict[str, int]:
    async with async_session() as session:
        result = await session.execute(text(deactivate_expired_listings_sql()))
        await session.commit()
    return {"deactivated": result.rowcount or 0}


async def cleanup_expired_listing_chunks(retention_days: int = 60) -> dict[str, int]:
    async with async_session() as session:
        result = await session.execute(
            text(cleanup_expired_listing_chunks_sql()),
            {"retention_days": retention_days},
        )
        await session.commit()
    return {"deleted_chunks": result.rowcount or 0}
```

- [ ] **Step 4: Add maintenance endpoints**

Append to `pipeline_worker/main.py`:

```python
from pipeline_worker.maintenance import cleanup_expired_listing_chunks, deactivate_expired_listings


@app.post("/internal/pipeline/maintenance/deactivate-expired-listings")
async def run_deactivate_expired_listings(
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    return {"result": await deactivate_expired_listings()}


@app.post("/internal/pipeline/maintenance/cleanup-expired-listing-chunks")
async def run_cleanup_expired_listing_chunks(
    payload: CleanupChunksRequest,
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    return {"result": await cleanup_expired_listing_chunks(payload.retention_days)}
```

- [ ] **Step 5: Run maintenance tests and API tests**

Run:

```powershell
python -m pytest backend\tests\test_pipeline_worker_maintenance.py backend\tests\test_pipeline_worker_api.py -q
```

Expected:

```text
4 passed
```

---

### Task 4: Build Pipeline Worker Docker Runtime

**Files:**
- Create: `pipeline_worker/requirements.txt`
- Create: `pipeline_worker/Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Create requirements**

Create `pipeline_worker/requirements.txt`:

```text
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
pydantic>=2.10.0
pydantic-settings>=2.7.0
python-dotenv>=1.0.0

sqlalchemy[asyncio]>=2.0.36
asyncpg>=0.30.0
pgvector>=0.3.6
alembic>=1.14.0

beautifulsoup4>=4.14.0
playwright>=1.58.0
playwright-stealth>=2.0.2
pymupdf>=1.24.0

google-genai>=1.0.0
httpx>=0.28.0
sentence-transformers>=3.0.0
```

- [ ] **Step 2: Create Dockerfile**

Create `pipeline_worker/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app:/app/backend
ENV HF_HOME=/app/.cache/huggingface
ENV HF_EMBEDDING_MODEL=BAAI/bge-m3

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY pipeline_worker/requirements.txt requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 300 --retries 10 -r requirements.txt
RUN python -m playwright install chromium
RUN python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ['HF_EMBEDDING_MODEL'])"

COPY pipeline_worker ./pipeline_worker
COPY backend ./backend
COPY crawler ./crawler
COPY data_pipeline ./data_pipeline

EXPOSE 8200
CMD ["uvicorn", "pipeline_worker.main:app", "--host", "0.0.0.0", "--port", "8200"]
```

- [ ] **Step 3: Add service to Docker Compose**

Add this service to `docker-compose.yml`:

```yaml
  pipeline-worker:
    build:
      context: .
      dockerfile: pipeline_worker/Dockerfile
    container_name: realestate_pipeline_worker
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-admin}:${POSTGRES_PASSWORD:-realestate_secret_2026}@postgres:5432/${POSTGRES_DB:-realestate}
      REDIS_URL: redis://redis:6379/0
      AGENT_INTERNAL_KEY: ${AGENT_INTERNAL_KEY}
      GEMINI_API_KEY: ${GEMINI_API_KEY:-}
      INTENT_EXTRACTOR: ${INTENT_EXTRACTOR:-rule}
      CHATBOT_EMBEDDING_LOCAL_FILES_ONLY: ${CHATBOT_EMBEDDING_LOCAL_FILES_ONLY:-true}
    volumes:
      - ./data:/app/data
    healthcheck:
      test: ["CMD-SHELL", "curl -f -H \"X-Internal-Agent-Key: $$AGENT_INTERNAL_KEY\" http://localhost:8200/internal/pipeline/health"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 30s
```

- [ ] **Step 4: Build pipeline worker**

Run:

```powershell
docker compose build pipeline-worker
```

Expected:

```text
pipeline-worker Built
```

---

### Task 5: Make Airflow Call Pipeline Worker

**Files:**
- Modify: `airflow/requirements.txt`
- Modify: `airflow/docker-compose.airflow.yml`
- Modify: `airflow/plugins/pipeline_runner.py`
- Modify: `airflow/dags/daily_listings_dag.py`
- Test: `backend/tests/test_pipeline_runner.py`

- [ ] **Step 1: Keep Airflow requirements light**

Set `airflow/requirements.txt` to:

```text
apache-airflow-providers-slack>=8.6.0,<9
```

- [ ] **Step 2: Point Airflow to Pipeline Worker**

In `airflow/docker-compose.airflow.yml`, set:

```yaml
    AGENT_INTERNAL_KEY: ${AGENT_INTERNAL_KEY}
    PIPELINE_WORKER_URL: http://pipeline-worker:8200
    PIPELINE_WORKER_DATA_ROOT: /app/data
```

- [ ] **Step 3: Write Airflow runner tests**

Update `backend/tests/test_pipeline_runner.py` so the HTTP call points to Pipeline Worker:

```python
def test_run_listings_ingestion_posts_to_pipeline_worker(monkeypatch):
    from plugins import pipeline_runner

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"result": {"published": 2, "indexed": 2, "chunks": 8}}'

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["payload"] = req.data.decode("utf-8")
        return FakeResponse()

    monkeypatch.setattr(pipeline_runner.request, "urlopen", fake_urlopen)

    result = pipeline_runner.run_listings_ingestion("/opt/project/data/raw/sale_details.csv", batch_size=25)

    assert captured["url"] == "http://pipeline-worker:8200/internal/pipeline/ingest/listings"
    assert '"csv_path": "/app/data/raw/sale_details.csv"' in captured["payload"]
    assert result["chunks"] == 8
```

- [ ] **Step 4: Implement Airflow runner**

In `airflow/plugins/pipeline_runner.py`, make the base URL and data root:

```python
PIPELINE_WORKER_URL = os.environ.get("PIPELINE_WORKER_URL", "http://pipeline-worker:8200").rstrip("/")
PIPELINE_WORKER_DATA_ROOT = os.environ.get("PIPELINE_WORKER_DATA_ROOT", "/app/data")
```

Use these in `_post_json()` and `_translate_backend_path()`.

- [ ] **Step 5: Ensure `daily_listings_dag` uses PythonOperator only**

In `airflow/dags/daily_listings_dag.py`, keep:

```python
mark_active = PythonOperator(
    task_id="mark_active",
    python_callable=_deactivate_expired_listings,
)

cleanup_expired_listing_chunks = PythonOperator(
    task_id="cleanup_expired_listing_chunks",
    python_callable=_cleanup_expired_listing_chunks,
)
```

- [ ] **Step 6: Run tests**

Run:

```powershell
python -m pytest backend\tests\test_pipeline_runner.py -q
```

Expected:

```text
all tests passed
```

---

### Task 6: Keep Backend and Agent Service Read-Only for Pipeline Data

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/rag/hybrid_search.py`
- Test: `backend/tests/test_hybrid_search.py`

- [ ] **Step 1: Remove temporary backend pipeline router**

If `backend/app/routers/internal_pipeline.py` exists from interim work, delete it and remove this import/include from `backend/app/main.py`:

```python
from app.routers import internal_pipeline
app.include_router(internal_pipeline.router)
```

- [ ] **Step 2: Keep Agent Service role unchanged**

Do not add crawler, ingestor, or chunking endpoints to `agent_service/main.py`. It should keep only:

```text
/internal/agent/health
/internal/agent/readiness
/internal/agent/chat
/internal/agent/evaluate
```

- [ ] **Step 3: Keep listing retrieval expiry guard**

In `backend/app/services/rag/hybrid_search.py`, `build_listing_filter_clauses()` must include:

```python
clauses = [
    "is_active = true",
    "("
    "expiry_date IS NULL OR expiry_date = '' OR "
    "CASE "
    "WHEN expiry_date ~ '^\\d{2}/\\d{2}/\\d{4}$' "
    "THEN to_date(expiry_date, 'DD/MM/YYYY') >= CURRENT_DATE "
    "WHEN expiry_date ~ '^\\d{4}-\\d{2}-\\d{2}$' "
    "THEN to_date(expiry_date, 'YYYY-MM-DD') >= CURRENT_DATE "
    "ELSE true "
    "END"
    ")",
]
```

- [ ] **Step 4: Run retrieval tests**

Run:

```powershell
python -m pytest backend\tests\test_hybrid_search.py -q
```

Expected:

```text
all tests passed
```

---

### Task 7: Verify Docker Compose Runtime

**Files:**
- No code files; verification only.

- [ ] **Step 1: Start base services**

Run:

```powershell
docker compose up -d postgres redis
```

Expected:

```text
realestate_postgres healthy
realestate_redis healthy
```

- [ ] **Step 2: Start pipeline worker**

Run:

```powershell
docker compose up -d --build pipeline-worker
```

Expected:

```text
realestate_pipeline_worker Up
```

- [ ] **Step 3: Check pipeline health**

Run:

```powershell
curl.exe -s -H "X-Internal-Agent-Key: local-agent-internal-key-realestate-v2-2026" http://localhost:8200/internal/pipeline/health
```

Expected:

```json
{"status":"ok","service":"pipeline-worker"}
```

- [ ] **Step 4: Start Airflow**

Run:

```powershell
docker compose -f airflow\docker-compose.airflow.yml up -d --build
```

Expected:

```text
airflow_webserver Up
airflow_scheduler Up
```

- [ ] **Step 5: Check Airflow UI**

Open:

```text
http://localhost:8080
```

Expected:

```text
Login works with admin/admin
daily_listings_dag, weekly_projects_dag, weekly_news_dag, monthly_legal_kb_dag are visible
```

---

### Task 8: End-to-End Smoke Test

**Files:**
- No code files; verification only.

- [ ] **Step 1: Trigger one small crawler task through Pipeline Worker**

Run:

```powershell
curl.exe -s -X POST http://localhost:8200/internal/pipeline/crawler `
  -H "Content-Type: application/json" `
  -H "X-Internal-Agent-Key: local-agent-internal-key-realestate-v2-2026" `
  -d "{\"module\":\"crawler.sale.crawl_urls\",\"args\":{\"--pages\":[\"1\",\"1\"],\"--output\":\"/app/data/raw/smoke_sale_urls.csv\",\"--workers\":\"1\"},\"timeout\":7200}"
```

Expected:

```json
{"stdout":"...","stderr":""}
```

- [ ] **Step 2: Confirm file exists on host**

Run:

```powershell
Test-Path data\raw\smoke_sale_urls.csv
```

Expected:

```text
True
```

- [ ] **Step 3: Confirm chatbot retrieval still uses Backend/Agent Service only**

Run:

```powershell
curl.exe -s http://localhost:8000/api/v1/health
```

Expected:

```json
{"status":"ok","version":"2.0.0"}
```

---

## Self-Review

Spec coverage:
- Airflow only schedules jobs: Task 5 and Task 7.
- Pipeline Worker handles crawl/ingest/chunk/embedding: Task 1, Task 2, Task 4.
- Legal documents are ingested without crawler: Task 2 `ingest/legal`.
- Expired listing maintenance and old chunk cleanup: Task 3.
- Backend and Agent Service remain read/query services: Task 6.
- Chatbot listing retrieval filters active and non-expired listings: Task 6.

Placeholder scan:
- No TBD/TODO placeholders.
- Every implementation task includes concrete files, code, commands, and expected output.

Type consistency:
- Internal key header is consistently `X-Internal-Agent-Key`.
- Pipeline Worker URL is consistently `PIPELINE_WORKER_URL`.
- Data path translation maps Airflow `/opt/project/data/...` to worker `/app/data/...`.
