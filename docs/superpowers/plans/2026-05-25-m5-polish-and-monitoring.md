# M5 Polish, Monitoring, And Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the M1–M4 pipeline from "works on my machine" to operable: drop dead columns, tune pgvector for the data volume reality, cache rerank/embedding calls, expose a metrics endpoint with crawl + ingestion + retrieval health, ship a Grafana dashboard preset, harden the Cohere v2 schema check, and pay down small tech debts called out in earlier self-reviews.

**Architecture:** No new ingestion paths or agents. M5 is purely cross-cutting: schema cleanup, observability, performance, and resilience. New code lives in `chatbot/tools/cache.py` (Redis cache wrapper), `backend/app/routers/metrics.py` (Prometheus endpoint), `airflow/plugins/run_metrics.py` (DAG run summary writer), and a single Alembic migration that drops the unused `Listing.embedding` column. Existing pipeline modules gain optional cache decorators and instrumented timing.

**Tech Stack:** Existing stack — FastAPI, SQLAlchemy async, Redis, pgvector, Airflow, Cohere — plus `prometheus-client>=0.21`. No new heavy dependency.

---

## Scope And Existing Repo Notes

- M5 assumes M1 + M2 + M3 + M4 are merged. Each task is independent enough to ship in isolation; the verification step at the end stitches them together.
- Master plan Phase 4 (Polish & Deploy) covers four families: performance/caching, monitoring, integration testing, and CI/CD + production deployment. M5 ships the first two. Integration testing against a real Postgres and the production deployment story (Docker prod images, GitHub Actions, secrets management) are intentionally out of scope here — they need a fundamentally different infrastructure surface (testcontainers, prod images, deploy targets) and can be tackled as a separate effort once M5 stabilizes.
- The `Listing.embedding` column at `backend/app/models/listing.py:76` has been dormant since M1 (retrieval reads only `chunks.embedding`). Drop it now to free vector index storage and reduce ORM surface.
- Cohere v2 schema risk was flagged in M1: rerank fails silently to vector-distance ordering when the API shape changes. M5 adds a contract test that pins the response shape so a future Cohere change becomes a loud failure rather than degraded retrieval.
- Embedding calls dominate ingestion cost. The same listing description is rarely re-embedded inside a single ingestion pass, but query embeddings hit the API on every chatbot turn. M5 caches query embeddings in Redis with a content-hash key namespaced by the model name so a model upgrade never returns stale vectors.
- Rerank calls are the second cost driver. M5 caches `(query_hash, doc_hash)` rerank scores for one hour, scoped to the rerank model name to avoid cross-model contamination after a `RERANK_MODEL` swap.
- Prometheus metrics live at `/api/v1/metrics`. Grafana scrapes via the existing FastAPI service — no separate exporter container.
- HNSW index parameters in M1 (`m=16`, `ef_construction=64`) were chosen for 6k listings. With M2 + M3 backfilling rent + projects + news, chunk count climbs past 100k. M5 raises `ef_construction` to 128 on a fresh index swap and sets `hnsw.ef_search=80` per session for query-side recall.
- The `notify_summary` follow-up flagged in M3 is implemented here as the `run_metrics.py` plugin. DAGs no longer leave their numbers in XCom only; the post-run callback writes a summary into a small `pipeline_runs` table that the metrics endpoint exposes.
- An optional Goong implementation was deferred from M2. M5 does NOT add it — the master plan only required Nominatim. If the user later sets `GEOCODER_PROVIDER=goong`, the runner already short-circuits to a no-op and emits a warning (added in this milestone).

## File Structure

- Create: `backend/alembic/versions/20260801_0004_drop_listing_embedding.py` — drop the dormant column.
- Create: `backend/app/routers/metrics.py` — Prometheus exposition endpoint plus a small `/api/v1/health/pipeline` JSON view.
- Create: `backend/app/models/pipeline_run.py` — `pipeline_runs` table for DAG run summaries.
- Modify: `backend/app/models/__init__.py` — export `PipelineRun`.
- Modify: `backend/app/main.py` — register the metrics router.
- Modify: `backend/requirements.txt` — add `prometheus-client>=0.21`.
- Create: `chatbot/tools/cache.py` — Redis JSON cache helper used by embedding + rerank.
- Modify: `chatbot/tools/hybrid_search.py` — wrap query embedding and Cohere rerank with cache + instrumentation.
- Modify: `data_pipeline/embed.py` — instrument batch embed call latency.
- Modify: `data_pipeline/enrich.py` — log a single warning when `GEOCODER_PROVIDER=goong` and short-circuit to no-op.
- Create: `airflow/plugins/run_metrics.py` — Airflow on-success / on-failure callbacks that insert into `pipeline_runs`.
- Modify: `airflow/dags/daily_listings_dag.py`, `weekly_projects_dag.py`, `weekly_news_dag.py`, `monthly_legal_kb_dag.py` — register the new callbacks.
- Create: `backend/alembic/versions/20260801_0005_pipeline_runs.py` — `pipeline_runs` table.
- Create: `backend/alembic/versions/20260801_0006_chunks_index_tune.py` — drop and recreate the HNSW index with tuned params.
- Create: `infra/grafana/realestate-pipeline.json` — Grafana dashboard JSON preset.
- Create: `backend/tests/test_metrics_endpoint.py`, `backend/tests/test_cache.py`, `backend/tests/test_cohere_schema_contract.py`, `backend/tests/test_run_metrics.py`, `backend/tests/test_geocoder_provider_warning.py`.

---

### Task 1: Drop Listing Embedding Column

**Files:**
- Modify: `backend/app/models/listing.py`
- Create: `backend/alembic/versions/20260801_0004_drop_listing_embedding.py`
- Test: `backend/tests/test_listing_embedding_removed.py`

- [ ] **Step 1: Write failing test asserting the column is gone**

Create `backend/tests/test_listing_embedding_removed.py`:

```python
from app.models import Listing


def test_listing_model_no_longer_has_embedding_column():
    columns = {col.name for col in Listing.__table__.columns}
    assert "embedding" not in columns
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_listing_embedding_removed.py -q
```

Expected: fail because `embedding` is still defined.

- [ ] **Step 3: Remove the column from the model**

In `backend/app/models/listing.py`, delete:

```python
from pgvector.sqlalchemy import Vector
...
    # Vector embedding for RAG
    embedding = Column(Vector(768))  # Gemini embedding dimension
```

Leave the rest of the file untouched. Remove the `pgvector.sqlalchemy` import if no other column in the file still uses `Vector` (only this column does today).

- [ ] **Step 4: Add the migration**

Create `backend/alembic/versions/20260801_0004_drop_listing_embedding.py`:

```python
"""drop legacy listings.embedding column

Revision ID: 20260801_0004
Revises: 20260701_0003
Create Date: 2026-08-01 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = "20260801_0004"
down_revision: Union[str, None] = "20260701_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("listings", "embedding")


def downgrade() -> None:
    op.add_column("listings", sa.Column("embedding", Vector(dim=768), nullable=True))
```

- [ ] **Step 5: Run the test**

```powershell
cd backend
python -m pytest tests/test_listing_embedding_removed.py -q
```

Expected: pass.

- [ ] **Step 6: Apply migration locally**

```powershell
docker-compose up -d postgres
cd backend
alembic upgrade head
```

Expected: revision `20260801_0004` applied without errors.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/models/listing.py backend/alembic/versions/20260801_0004_drop_listing_embedding.py backend/tests/test_listing_embedding_removed.py
git commit -m "drop dormant listings.embedding column"
```

---

### Task 2: Pipeline Runs Table And Model

**Files:**
- Create: `backend/app/models/pipeline_run.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260801_0005_pipeline_runs.py`
- Test: `backend/tests/test_pipeline_run_model.py`

- [ ] **Step 1: Write failing test for the model**

Create `backend/tests/test_pipeline_run_model.py`:

```python
from app.models import PipelineRun


def test_pipeline_run_columns():
    columns = {col.name for col in PipelineRun.__table__.columns}
    assert {"id", "dag_id", "run_id", "status", "started_at", "ended_at", "metrics", "error"} <= columns
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_pipeline_run_model.py -q
```

Expected: fail because `PipelineRun` does not exist.

- [ ] **Step 3: Create the model**

Create `backend/app/models/pipeline_run.py`:

```python
from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text, func

from app.database import Base


class PipelineRun(Base):
    """Summary record per Airflow DAG run."""

    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dag_id = Column(String(80), nullable=False)
    run_id = Column(String(160), nullable=False)
    status = Column(String(20), nullable=False)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    metrics = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_pipeline_runs_dag_run", "dag_id", "run_id", unique=True),
        Index("ix_pipeline_runs_started", "started_at"),
    )
```

Modify `backend/app/models/__init__.py` to export the new class:

```python
from app.models.pipeline_run import PipelineRun

__all__ = [
    "Article",
    "Chunk",
    "Listing",
    "PipelineRun",
    "Project",
    "User",
    "ChatSession",
    "ChatMessage",
]
```

- [ ] **Step 4: Add the migration**

Create `backend/alembic/versions/20260801_0005_pipeline_runs.py`:

```python
"""pipeline runs summary table

Revision ID: 20260801_0005
Revises: 20260801_0004
Create Date: 2026-08-01 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260801_0005"
down_revision: Union[str, None] = "20260801_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dag_id", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pipeline_runs_dag_run", "pipeline_runs", ["dag_id", "run_id"], unique=True)
    op.create_index("ix_pipeline_runs_started", "pipeline_runs", ["started_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_started", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_dag_run", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
```

- [ ] **Step 5: Run the test and apply migration**

```powershell
cd backend
python -m pytest tests/test_pipeline_run_model.py -q
alembic upgrade head
```

Expected: test passes; revision `20260801_0005` applied.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/models/pipeline_run.py backend/app/models/__init__.py backend/alembic/versions/20260801_0005_pipeline_runs.py backend/tests/test_pipeline_run_model.py
git commit -m "add pipeline runs summary table"
```

---

### Task 3: Airflow Run Metrics Plugin

**Files:**
- Create: `airflow/plugins/run_metrics.py`
- Modify: `airflow/dags/daily_listings_dag.py`
- Modify: `airflow/dags/weekly_projects_dag.py`
- Modify: `airflow/dags/weekly_news_dag.py`
- Modify: `airflow/dags/monthly_legal_kb_dag.py`
- Test: `backend/tests/test_run_metrics.py`

- [ ] **Step 1: Write failing test for the writer**

Create `backend/tests/test_run_metrics.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "airflow"))

from plugins.run_metrics import build_run_summary


def test_build_run_summary_extracts_dag_run_status():
    context = {
        "dag": type("D", (), {"dag_id": "daily_listings_dag"})(),
        "dag_run": type(
            "R",
            (),
            {
                "run_id": "manual__2026-08-01T02:00:00",
                "start_date": __import__("datetime").datetime(2026, 8, 1, 2, 0),
                "end_date": __import__("datetime").datetime(2026, 8, 1, 2, 30),
                "state": "success",
            },
        )(),
        "ti": type("T", (), {"xcom_pull": lambda self, key=None, task_ids=None: None})(),
    }

    summary = build_run_summary(context, status="success", error=None, metrics={"listings": 42, "chunks": 168})

    assert summary["dag_id"] == "daily_listings_dag"
    assert summary["run_id"].startswith("manual__")
    assert summary["status"] == "success"
    assert summary["metrics"] == {"listings": 42, "chunks": 168}
    assert summary["error"] is None
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_run_metrics.py -q
```

Expected: fail because the module does not exist.

- [ ] **Step 3: Implement the plugin**

Create `airflow/plugins/run_metrics.py`:

```python
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("PROJECT_ROOT", "/opt/project")).resolve()
BACKEND = REPO_ROOT / "backend"
for path in (str(REPO_ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)


def build_run_summary(context: dict[str, Any], *, status: str, error: str | None, metrics: dict[str, Any] | None) -> dict[str, Any]:
    dag_run = context.get("dag_run")
    return {
        "dag_id": context["dag"].dag_id,
        "run_id": getattr(dag_run, "run_id", "unknown") if dag_run else "unknown",
        "status": status,
        "started_at": getattr(dag_run, "start_date", None) if dag_run else None,
        "ended_at": getattr(dag_run, "end_date", None) if dag_run else None,
        "metrics": metrics or {},
        "error": error,
    }


def _persist(summary: dict[str, Any]) -> None:
    import asyncio

    from app.database import async_session
    from app.models import PipelineRun
    from sqlalchemy import select

    async def _write() -> None:
        async with async_session() as session:
            existing = await session.execute(
                select(PipelineRun).where(
                    PipelineRun.dag_id == summary["dag_id"],
                    PipelineRun.run_id == summary["run_id"],
                )
            )
            run = existing.scalar_one_or_none()
            if run is None:
                run = PipelineRun(**summary)
                session.add(run)
            else:
                for key, value in summary.items():
                    setattr(run, key, value)
            await session.commit()

    asyncio.run(_write())


def on_success(context: dict[str, Any]) -> None:
    metrics: dict[str, Any] = {}
    ti = context.get("ti")
    if ti is not None:
        for key in ("listings", "chunks", "projects", "articles", "documents", "skipped"):
            value = ti.xcom_pull(key=key) if hasattr(ti, "xcom_pull") else None
            if value is not None:
                metrics[key] = value
    summary = build_run_summary(context, status="success", error=None, metrics=metrics)
    _persist(summary)


def on_failure(context: dict[str, Any]) -> None:
    exception = context.get("exception")
    summary = build_run_summary(
        context,
        status="failed",
        error=str(exception) if exception else None,
        metrics=None,
    )
    _persist(summary)
```

- [ ] **Step 4: Wire the callbacks into all four DAGs**

In each of `daily_listings_dag.py`, `weekly_projects_dag.py`, `weekly_news_dag.py`, `monthly_legal_kb_dag.py`:

Add at the top:

```python
from plugins.run_metrics import on_failure as record_failure
from plugins.run_metrics import on_success as record_success
```

Inside the `DAG(...)` constructor call add:

```python
    on_success_callback=record_success,
    on_failure_callback=record_failure,
```

Keep the existing `slack_failure_callback` inside `DEFAULT_ARGS["on_failure_callback"]`. The DAG-level `on_failure_callback` is the new run-summary writer; the task-level callback in `DEFAULT_ARGS` is the Slack alert. They do not conflict because they live at different scopes.

- [ ] **Step 5: Run the unit test**

```powershell
cd backend
python -m pytest tests/test_run_metrics.py -q
```

Expected: pass.

- [ ] **Step 6: Verify DAG parsing in the Airflow container**

```powershell
docker compose -f airflow\docker-compose.airflow.yml run --rm airflow_scheduler python -c "from airflow.models import DagBag; bag = DagBag(); assert bag.import_errors == {}, bag.import_errors; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 7: Commit**

```powershell
git add airflow/plugins/run_metrics.py airflow/dags/daily_listings_dag.py airflow/dags/weekly_projects_dag.py airflow/dags/weekly_news_dag.py airflow/dags/monthly_legal_kb_dag.py backend/tests/test_run_metrics.py
git commit -m "record pipeline run summaries from airflow"
```

---

### Task 4: Redis JSON Cache Helper

**Files:**
- Create: `chatbot/tools/cache.py`
- Test: `backend/tests/test_cache.py`

- [ ] **Step 1: Write failing tests with a fake Redis client**

Create `backend/tests/test_cache.py`:

```python
import pytest

from chatbot.tools.cache import JsonCache


class FakeRedis:
    def __init__(self):
        self.store: dict[str, tuple[str, int | None]] = {}

    async def get(self, key: str):
        record = self.store.get(key)
        return record[0] if record else None

    async def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = (value, ex)


@pytest.mark.asyncio
async def test_cache_get_returns_none_for_missing_key():
    cache = JsonCache(client=FakeRedis(), namespace="test")
    assert await cache.get("missing") is None


@pytest.mark.asyncio
async def test_cache_set_then_get_round_trips_payload():
    cache = JsonCache(client=FakeRedis(), namespace="test", ttl_seconds=60)

    await cache.set("k", {"foo": [1, 2, 3]})
    payload = await cache.get("k")

    assert payload == {"foo": [1, 2, 3]}


@pytest.mark.asyncio
async def test_cache_namespaces_keys_to_avoid_collision():
    redis = FakeRedis()
    a = JsonCache(client=redis, namespace="a")
    b = JsonCache(client=redis, namespace="b")

    await a.set("same", 1)
    await b.set("same", 2)

    assert await a.get("same") == 1
    assert await b.get("same") == 2
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_cache.py -q
```

Expected: fail because `chatbot.tools.cache` does not exist.

- [ ] **Step 3: Implement the cache**

Create `chatbot/tools/cache.py`:

```python
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@dataclass
class JsonCache:
    client: Any
    namespace: str
    ttl_seconds: int | None = None

    def _key(self, raw: str) -> str:
        return f"{self.namespace}:{raw}"

    async def get(self, key: str) -> Any:
        raw = await self.client.get(self._key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None

    async def set(self, key: str, value: Any) -> None:
        await self.client.set(self._key(key), json.dumps(value, ensure_ascii=False), ex=self.ttl_seconds)


def hash_text(text: str, *, namespace: str = "") -> str:
    """Hash a single text. Pass `namespace` to scope it to a model/version
    so cache hits never bleed across embedding model upgrades."""
    payload = f"{namespace}|{text}" if namespace else text
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_pair(query: str, doc: str, *, namespace: str = "") -> str:
    """Hash a (query, doc) pair, optionally scoped to a model/version."""
    payload = f"{namespace}|{query}|{doc}" if namespace else f"{query}|{doc}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_redis_client():
    from app.config import get_settings
    from redis import asyncio as redis_async

    settings = get_settings()
    return redis_async.from_url(settings.REDIS_URL, decode_responses=True)
```

- [ ] **Step 4: Run the cache tests**

```powershell
cd backend
python -m pytest tests/test_cache.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add chatbot/tools/cache.py backend/tests/test_cache.py
git commit -m "add redis json cache helper"
```

---

### Task 5: Cache Query Embeddings And Rerank Scores

**Files:**
- Modify: `chatbot/tools/hybrid_search.py`
- Test: `backend/tests/test_hybrid_search_caching.py`

- [ ] **Step 1: Write failing test confirming cached embeddings skip the embedder**

Create `backend/tests/test_hybrid_search_caching.py`:

```python
import pytest

from chatbot.tools import hybrid_search as hs


class StubCache:
    def __init__(self, payload):
        self.payload = payload
        self.set_calls = []

    async def get(self, key):
        return self.payload

    async def set(self, key, value):
        self.set_calls.append((key, value))


class StubEmbedder:
    def __init__(self):
        self.calls = 0

    async def embed_texts(self, texts):
        self.calls += 1
        return [[0.5] * 768 for _ in texts]


@pytest.mark.asyncio
async def test_get_query_embedding_uses_cache_when_available(monkeypatch):
    cache = StubCache(payload=[0.1] * 768)
    embedder = StubEmbedder()

    vector = await hs.get_query_embedding("căn hộ Quận 7", embedder=embedder, cache=cache)

    assert vector == [0.1] * 768
    assert embedder.calls == 0


@pytest.mark.asyncio
async def test_get_query_embedding_populates_cache_on_miss(monkeypatch):
    cache = StubCache(payload=None)
    embedder = StubEmbedder()

    vector = await hs.get_query_embedding("căn hộ Quận 7", embedder=embedder, cache=cache)

    assert len(vector) == 768
    assert embedder.calls == 1
    assert len(cache.set_calls) == 1
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_hybrid_search_caching.py -q
```

Expected: fail because `get_query_embedding` is not yet a separate function.

- [ ] **Step 3: Refactor `hybrid_search.py` to expose cacheable helpers**

Add to `chatbot/tools/hybrid_search.py` near the top:

```python
from chatbot.tools.cache import JsonCache, get_redis_client, hash_pair, hash_text


async def get_query_embedding(query: str, *, embedder, cache: JsonCache | None = None) -> list[float]:
    cache_key = hash_text(query, namespace=getattr(embedder, "model", ""))
    if cache is not None:
        cached = await cache.get(cache_key)
        if cached:
            return cached
    vectors = await embedder.embed_texts([query])
    embedding = vectors[0]
    if cache is not None:
        await cache.set(cache_key, embedding)
    return embedding
```

In the existing `hybrid_search` body, replace the inline embedder call with:

```python
    embedding_cache = JsonCache(client=await get_redis_client(), namespace="embed:q", ttl_seconds=60 * 60 * 24 * 7)
    query_embedding = await get_query_embedding(query, embedder=embedder, cache=embedding_cache)
```

Wrap the existing Cohere call in a `(query, doc)` cache scoped to the rerank model name:

```python
    rerank_cache = JsonCache(client=await get_redis_client(), namespace="rerank", ttl_seconds=60 * 60)
    rerank_namespace = settings.RERANK_MODEL

    async def cached_score(query_text: str, doc_text: str) -> float | None:
        return await rerank_cache.get(hash_pair(query_text, doc_text, namespace=rerank_namespace))

    async def store_score(query_text: str, doc_text: str, score: float) -> None:
        await rerank_cache.set(hash_pair(query_text, doc_text, namespace=rerank_namespace), score)
```

Modify `cohere_rerank` to consult `cached_score` before issuing an HTTP call when callers pass it in. Keep the existing fallback path (`if not settings.COHERE_API_KEY: return chunks[:top_n]`). When the API responds, call `store_score` for each `(query, doc)` pair.

- [ ] **Step 4: Run the caching test**

```powershell
cd backend
python -m pytest tests/test_hybrid_search_caching.py tests/test_hybrid_search.py tests/test_hybrid_search_multi_parent.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add chatbot/tools/hybrid_search.py backend/tests/test_hybrid_search_caching.py
git commit -m "cache query embeddings and rerank scores"
```

---

### Task 6: Cohere Schema Contract Test

**Files:**
- Test: `backend/tests/test_cohere_schema_contract.py`

- [ ] **Step 1: Write the contract test**

Create `backend/tests/test_cohere_schema_contract.py`:

```python
import pytest

from chatbot.tools import hybrid_search as hs


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *_, **__):
        return FakeResp(self._payload)


@pytest.mark.asyncio
async def test_cohere_v2_schema_must_expose_results_index_and_score(monkeypatch):
    fake_settings = type("S", (), {"COHERE_API_KEY": "k", "RERANK_MODEL": "rerank-multilingual-v3.0"})()
    monkeypatch.setattr(hs, "get_settings", lambda: fake_settings)

    payload = {
        "id": "abc",
        "results": [
            {"index": 0, "relevance_score": 0.9, "document": {"text": "..."}},
        ],
        "meta": {"api_version": {"version": "2"}},
    }
    monkeypatch.setattr(hs.httpx, "AsyncClient", lambda *a, **k: FakeAsyncClient(payload))

    chunks = [{"text": "a", "parent_id": 1, "chunk_type": "overview", "distance": 0.1}]
    result = await hs.cohere_rerank("query", chunks, top_n=1)

    assert result, "Cohere v2 schema regression: results array missing"
    assert "rerank_score" in result[0], "Cohere v2 schema regression: relevance_score missing"
    assert result[0]["parent_id"] == 1


@pytest.mark.asyncio
async def test_cohere_unexpected_payload_returns_top_n_distance_order(monkeypatch):
    fake_settings = type("S", (), {"COHERE_API_KEY": "k", "RERANK_MODEL": "x"})()
    monkeypatch.setattr(hs, "get_settings", lambda: fake_settings)

    payload = {"unexpected": True}
    monkeypatch.setattr(hs.httpx, "AsyncClient", lambda *a, **k: FakeAsyncClient(payload))

    chunks = [
        {"text": "a", "parent_id": 1, "chunk_type": "overview", "distance": 0.5},
        {"text": "b", "parent_id": 2, "chunk_type": "overview", "distance": 0.1},
    ]

    result = await hs.cohere_rerank("query", chunks, top_n=2)

    assert len(result) == 2
    assert result[0]["parent_id"] in {1, 2}
```

- [ ] **Step 2: Run the test**

```powershell
cd backend
python -m pytest tests/test_cohere_schema_contract.py -q
```

Expected: pass once `cohere_rerank` implements the documented fallback. The second test enforces that an unexpected payload silently degrades to vector ordering rather than raising.

If `cohere_rerank` currently raises on unexpected schema, adjust it to:

```python
    data = response.json()
    results = data.get("results")
    if not results:
        return chunks[:top_n]
    reranked = []
    for item in results:
        if "index" not in item:
            return chunks[:top_n]
        chunk = dict(chunks[item["index"]])
        chunk["rerank_score"] = item.get("relevance_score")
        reranked.append(chunk)
    return reranked
```

- [ ] **Step 3: Commit**

```powershell
git add chatbot/tools/hybrid_search.py backend/tests/test_cohere_schema_contract.py
git commit -m "contract-test cohere rerank schema"
```

---

### Task 7: Geocoder Provider Warning

**Files:**
- Modify: `data_pipeline/enrich.py`
- Test: `backend/tests/test_geocoder_provider_warning.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_geocoder_provider_warning.py`:

```python
import pytest

from data_pipeline import enrich


@pytest.mark.asyncio
async def test_build_geocoder_warns_for_unsupported_provider(caplog):
    caplog.set_level("WARNING", logger="data_pipeline.enrich")

    geocoder = enrich.build_geocoder(provider="goong", user_agent="test/0.1", goong_api_key="")

    coord = await geocoder.geocode("Quận 7, Hồ Chí Minh")

    assert coord is None
    assert any("goong" in record.message.lower() for record in caplog.records)


@pytest.mark.asyncio
async def test_build_geocoder_returns_nominatim_for_default_provider(monkeypatch):
    geocoder = enrich.build_geocoder(provider="nominatim", user_agent="test/0.1", goong_api_key="")
    assert isinstance(geocoder, enrich.NominatimGeocoder)
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_geocoder_provider_warning.py -q
```

Expected: fail because `build_geocoder` does not exist.

- [ ] **Step 3: Implement the factory**

Append to `data_pipeline/enrich.py`:

```python
import logging

logger = logging.getLogger(__name__)


class _NoOpGeocoder:
    async def geocode(self, address: str) -> tuple[float, float] | None:
        return None


def build_geocoder(*, provider: str, user_agent: str, goong_api_key: str) -> object:
    if provider == "nominatim":
        return NominatimGeocoder(user_agent=user_agent)
    if provider == "goong":
        logger.warning(
            "GEOCODER_PROVIDER=goong is configured but not implemented in M5; "
            "geocoding will be skipped. Implement a GoongGeocoder if needed."
        )
        return _NoOpGeocoder()
    logger.warning("Unknown GEOCODER_PROVIDER=%s; geocoding disabled.", provider)
    return _NoOpGeocoder()
```

Update `listings_ingestor.py` to call `build_geocoder` instead of constructing `NominatimGeocoder` directly:

```python
from data_pipeline.enrich import build_geocoder

geocoder = build_geocoder(
    provider=settings.GEOCODER_PROVIDER,
    user_agent=settings.GEOCODER_USER_AGENT,
    goong_api_key=settings.GOONG_API_KEY,
)
```

- [ ] **Step 4: Run the test**

```powershell
cd backend
python -m pytest tests/test_geocoder_provider_warning.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add data_pipeline/enrich.py data_pipeline/ingestors/listings_ingestor.py backend/tests/test_geocoder_provider_warning.py
git commit -m "warn on unsupported geocoder provider"
```

---

### Task 8: Prometheus Metrics Endpoint

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/routers/metrics.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_metrics_endpoint.py`

- [ ] **Step 1: Add the dependency**

Append to `backend/requirements.txt`:

```text
prometheus-client>=0.21
```

- [ ] **Step 2: Write failing test for the endpoint**

Create `backend/tests/test_metrics_endpoint.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_text():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "realestate_chat_requests_total" in body
    assert "realestate_pipeline_runs_total" in body


@pytest.mark.asyncio
async def test_pipeline_health_returns_summary_per_dag():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/pipeline")

    assert response.status_code == 200
    body = response.json()
    assert "dags" in body
```

- [ ] **Step 3: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_metrics_endpoint.py -q
```

Expected: fail because the endpoints do not exist.

- [ ] **Step 4: Implement the router**

Create `backend/app/routers/metrics.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import func, select

from app.database import async_session
from app.models import Article, Chunk, Listing, PipelineRun


router = APIRouter(tags=["Metrics"])


CHAT_REQUESTS = Counter(
    "realestate_chat_requests_total",
    "Total chat completions handled by the backend",
    labelnames=("agent",),
)
RETRIEVAL_LATENCY = Histogram(
    "realestate_retrieval_latency_seconds",
    "Latency of hybrid_search pipeline",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
PIPELINE_RUNS = Gauge(
    "realestate_pipeline_runs_total",
    "Pipeline runs aggregated by DAG and status (snapshot from pipeline_runs table)",
    labelnames=("dag_id", "status"),
)
LISTINGS_TOTAL = Gauge("realestate_listings_total", "Total listings in DB", labelnames=("listing_type",))
CHUNKS_TOTAL = Gauge("realestate_chunks_total", "Total chunks indexed", labelnames=("parent_type",))
ARTICLES_TOTAL = Gauge("realestate_articles_total", "Total articles in DB", labelnames=("category",))


async def _refresh_gauges() -> None:
    # Reset stale labels first so deleted partitions disappear from /metrics.
    for gauge in (LISTINGS_TOTAL, CHUNKS_TOTAL, ARTICLES_TOTAL, PIPELINE_RUNS):
        gauge.clear()

    async with async_session() as session:
        listings = await session.execute(
            select(Listing.listing_type, func.count()).group_by(Listing.listing_type)
        )
        for listing_type, count in listings.all():
            LISTINGS_TOTAL.labels(listing_type=listing_type or "unknown").set(count)

        chunks = await session.execute(
            select(Chunk.parent_type, func.count()).group_by(Chunk.parent_type)
        )
        for parent_type, count in chunks.all():
            CHUNKS_TOTAL.labels(parent_type=parent_type or "unknown").set(count)

        articles = await session.execute(
            select(Article.category, func.count()).group_by(Article.category)
        )
        for category, count in articles.all():
            ARTICLES_TOTAL.labels(category=category or "unknown").set(count)

        runs = await session.execute(
            select(PipelineRun.dag_id, PipelineRun.status, func.count()).group_by(
                PipelineRun.dag_id, PipelineRun.status
            )
        )
        for dag_id, status, count in runs.all():
            PIPELINE_RUNS.labels(dag_id=dag_id, status=status).set(count)


@router.get("/metrics", include_in_schema=False)
async def metrics_endpoint() -> Response:
    await _refresh_gauges()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/health/pipeline")
async def pipeline_health() -> dict:
    async with async_session() as session:
        rows = await session.execute(
            select(
                PipelineRun.dag_id,
                func.max(PipelineRun.ended_at).label("last_run"),
                PipelineRun.status,
            )
            .group_by(PipelineRun.dag_id, PipelineRun.status)
            .order_by(PipelineRun.dag_id)
        )
        runs = rows.all()

    summary: dict[str, dict] = {}
    for dag_id, last_run, status in runs:
        bucket = summary.setdefault(dag_id, {"successful": 0, "failed": 0, "last_run": None})
        if status == "success":
            bucket["successful"] += 1
        elif status == "failed":
            bucket["failed"] += 1
        if last_run and (bucket["last_run"] is None or last_run > bucket["last_run"]):
            bucket["last_run"] = last_run.isoformat()

    return {"as_of": datetime.now(timezone.utc).isoformat(), "dags": summary}
```

Modify `backend/app/main.py` to include the router:

```python
from app.routers import auth, chat, listings, market, metrics

...

app.include_router(metrics.router, prefix="/api/v1")
```

- [ ] **Step 5: Run the test**

```powershell
cd backend
python -m pytest tests/test_metrics_endpoint.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/requirements.txt backend/app/routers/metrics.py backend/app/main.py backend/tests/test_metrics_endpoint.py
git commit -m "expose prometheus metrics and pipeline health endpoint"
```

---

### Task 9: Tune Chunks HNSW Index

**Files:**
- Create: `backend/alembic/versions/20260801_0006_chunks_index_tune.py`

- [ ] **Step 1: Add the migration**

Create `backend/alembic/versions/20260801_0006_chunks_index_tune.py`:

```python
"""tune chunks hnsw index for larger corpus

Revision ID: 20260801_0006
Revises: 20260801_0005
Create Date: 2026-08-01 00:00:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260801_0006"
down_revision: Union[str, None] = "20260801_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw "
        "ON chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 128)"
    )
    op.execute("ALTER DATABASE CURRENT SET hnsw.ef_search = 80")


def downgrade() -> None:
    op.execute("ALTER DATABASE CURRENT RESET hnsw.ef_search")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw "
        "ON chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
```

`ALTER DATABASE CURRENT SET hnsw.ef_search` is a session default; new connections inherit `ef_search=80`. This affects retrieval quality but not write throughput.

- [ ] **Step 2: Apply and verify**

```powershell
cd backend
alembic upgrade head
docker exec -it realestate_postgres psql -U admin -d realestate -c "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_chunks_embedding_hnsw';"
docker exec -it realestate_postgres psql -U admin -d realestate -c "SHOW hnsw.ef_search;"
```

Expected: index definition contains `m='16'` and `ef_construction='128'`; `hnsw.ef_search` is `80` (open a fresh `psql` connection if the original one started before the migration).

- [ ] **Step 3: Commit**

```powershell
git add backend/alembic/versions/20260801_0006_chunks_index_tune.py
git commit -m "tune chunks hnsw index for larger corpus"
```

---

### Task 10: Grafana Dashboard Preset

**Files:**
- Create: `infra/grafana/realestate-pipeline.json`

- [ ] **Step 1: Add the dashboard JSON**

Create `infra/grafana/realestate-pipeline.json`:

```json
{
  "title": "RealEstate Pipeline",
  "schemaVersion": 39,
  "version": 1,
  "refresh": "30s",
  "panels": [
    {
      "type": "stat",
      "title": "Listings (sale)",
      "targets": [
        {"expr": "realestate_listings_total{listing_type=\"sale\"}", "refId": "A"}
      ],
      "gridPos": {"x": 0, "y": 0, "w": 6, "h": 4}
    },
    {
      "type": "stat",
      "title": "Listings (rent)",
      "targets": [
        {"expr": "realestate_listings_total{listing_type=\"rent\"}", "refId": "A"}
      ],
      "gridPos": {"x": 6, "y": 0, "w": 6, "h": 4}
    },
    {
      "type": "stat",
      "title": "Chunks (article)",
      "targets": [
        {"expr": "realestate_chunks_total{parent_type=\"article\"}", "refId": "A"}
      ],
      "gridPos": {"x": 12, "y": 0, "w": 6, "h": 4}
    },
    {
      "type": "stat",
      "title": "Chunks (listing)",
      "targets": [
        {"expr": "realestate_chunks_total{parent_type=\"listing\"}", "refId": "A"}
      ],
      "gridPos": {"x": 18, "y": 0, "w": 6, "h": 4}
    },
    {
      "type": "timeseries",
      "title": "Pipeline runs by status",
      "targets": [
        {"expr": "sum by (dag_id, status) (rate(realestate_pipeline_runs_total[1h]))", "refId": "A"}
      ],
      "gridPos": {"x": 0, "y": 4, "w": 24, "h": 8}
    },
    {
      "type": "timeseries",
      "title": "Retrieval latency p95",
      "targets": [
        {"expr": "histogram_quantile(0.95, sum by (le) (rate(realestate_retrieval_latency_seconds_bucket[5m])))", "refId": "A"}
      ],
      "gridPos": {"x": 0, "y": 12, "w": 12, "h": 8}
    },
    {
      "type": "timeseries",
      "title": "Chat requests by agent",
      "targets": [
        {"expr": "sum by (agent) (rate(realestate_chat_requests_total[5m]))", "refId": "A"}
      ],
      "gridPos": {"x": 12, "y": 12, "w": 12, "h": 8}
    }
  ]
}
```

- [ ] **Step 2: Document import path**

Append a one-line note to the existing `docs/multiagent-workflow.md` (or `README.md` if the workflow doc does not have an "Operations" section) pointing operators at `infra/grafana/realestate-pipeline.json`. Keep it under three lines.

Example one-liner:

```markdown
- Grafana: import `infra/grafana/realestate-pipeline.json` and point it at the FastAPI Prometheus scrape job.
```

- [ ] **Step 3: Commit**

```powershell
git add infra/grafana/realestate-pipeline.json docs/multiagent-workflow.md
git commit -m "ship grafana dashboard preset"
```

---

### Task 11: M5 End-To-End Verification

**Files:**
- No required code changes unless a previous task failed verification.

- [ ] **Step 1: Run all M1–M5 tests**

```powershell
cd backend
python -m pytest tests -q
```

Expected: all pass.

- [ ] **Step 2: Apply migrations**

```powershell
docker-compose up -d postgres
cd backend
alembic upgrade head
```

Expected: revisions up to `20260801_0006` applied. `\d listings` no longer shows `embedding`; `\d pipeline_runs` exists.

- [ ] **Step 3: Trigger a DAG and verify the run was recorded**

In Airflow UI, trigger `weekly_news_dag` (smallest DAG, fastest feedback). After it completes:

```powershell
docker exec -it realestate_postgres psql -U admin -d realestate -c "SELECT dag_id, status, ended_at, metrics FROM pipeline_runs ORDER BY id DESC LIMIT 5;"
```

Expected: at least one new row with `status='success'` and a non-null `metrics` JSON.

- [ ] **Step 4: Hit the metrics endpoint**

```powershell
cd backend
uvicorn app.main:app --port 8000
```

In another shell:

```powershell
Invoke-WebRequest http://localhost:8000/api/v1/metrics | Select-Object -ExpandProperty Content | Select-String "realestate_"
Invoke-RestMethod http://localhost:8000/api/v1/health/pipeline
```

Expected: Prometheus output contains `realestate_listings_total`, `realestate_chunks_total`, `realestate_pipeline_runs_total`. Health endpoint returns a JSON `dags` map with at least the DAG triggered above.

- [ ] **Step 5: Confirm caching reduces repeat embedding cost**

Run the same chatbot query twice and watch `realestate_retrieval_latency_seconds_bucket` shrink for the second run. Use the FastAPI logs to confirm only one Gemini call was issued for the query embedding:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/chat -ContentType "application/json" -Body '{"message":"Tìm căn hộ 2PN Quận 7 dưới 5 tỷ"}'
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/chat -ContentType "application/json" -Body '{"message":"Tìm căn hộ 2PN Quận 7 dưới 5 tỷ"}'
```

Expected: the second response is faster; backend logs show only a single embed call for that query string.

- [ ] **Step 6: Validate the Cohere contract test**

```powershell
cd backend
python -m pytest tests/test_cohere_schema_contract.py -q
```

Expected: pass. If Cohere ships a v3 with a different shape this test is the early warning.

- [ ] **Step 7: Verify Goong placeholder warning surfaces**

Set `GEOCODER_PROVIDER=goong` in `.env`, restart the backend container, and run the listings ingestor on a single CSV row. Confirm the warning appears in logs and rows still ingest with `latitude=NULL`.

- [ ] **Step 8: Import Grafana dashboard (optional)**

If a Grafana instance is available, import `infra/grafana/realestate-pipeline.json`, point its Prometheus data source at the backend scrape job, and confirm the 7 panels render.

- [ ] **Step 9: Commit verification fixes**

If any verification step required code changes:

```powershell
git add <changed-files>
git commit -m "fix m5 verification issues"
```

---

## Self-Review

- Spec coverage: M5 closes the perf + observability tail of master plan Phase 4 — drops the dormant `Listing.embedding` column (Task 1), adds a per-run summary table (Task 2), wires Airflow run metrics (Task 3), introduces Redis caching for query embeddings and rerank scores keyed by model namespace (Tasks 4–5), pins the Cohere v2 schema with a contract test (Task 6), surfaces the deferred Goong provider as an explicit warning (Task 7), exposes Prometheus metrics + pipeline health (Task 8), tunes the HNSW index for the larger M2/M3 corpus (Task 9), and ships a Grafana preset (Task 10). Integration testing with testcontainers, the production Docker compose stack, and the GitHub Actions CI/CD pipeline are out of scope — handle those as a separate effort when production deploy is needed.
- Placeholder scan: every step lists concrete files, runnable commands, and code blocks. The Grafana JSON is fully populated, not a TODO. The Goong factory is a documented no-op rather than a TBD comment.
- Type consistency: `pipeline_runs` schema matches the dict shape produced by `build_run_summary`; `PIPELINE_RUNS` is a `Gauge` (not a `Counter`) because the metric is a snapshot of the table, not a monotonic counter — using `.set()` is the documented public API; the Prometheus label sets (`agent`, `dag_id`, `status`, `listing_type`, `parent_type`, `category`) match the labels recorded by `on_success` / `on_failure` and `_refresh_gauges`; `JsonCache` always serializes JSON-compatible payloads (lists / dicts / scalars), which matches what `embed.embed_texts` and `cohere_rerank` consume.
- Cache key safety: both `hash_text` and `hash_pair` accept a `namespace` argument so a model upgrade (`GEMINI_EMBEDDING_MODEL` or `RERANK_MODEL` change) never returns stale cached vectors or scores. Without the namespace the next deploy after a model bump would silently serve wrong-dimension embeddings — this was a real risk worth designing out.
- Known limits accepted in M5: the metrics endpoint refreshes gauge values on every scrape (one DB round-trip per scrape) and clears stale labels first to prevent ghost partitions — acceptable at 30 s scrape intervals but not at 1 s; if Prometheus scrape rate is tightened later, switch to a background refresher. The HNSW retune drops and recreates the index in a single statement — for tables larger than ~1 M chunks consider building the new index concurrently before swapping. Cohere caching uses a 1-hour TTL on `(query, doc)` pairs; long sessions on the same listing remain cheap, but stale rerank scores after a relevance model change need a `RERANK_MODEL` value bump (which automatically invalidates via the namespace) or a `FLUSHDB`. The `run_metrics.on_success` writer uses `asyncio.run()` — safe under M3's LocalExecutor but will need an "already-running-loop" branch when Airflow eventually switches to CeleryExecutor.