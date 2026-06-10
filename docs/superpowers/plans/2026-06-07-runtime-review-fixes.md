# Runtime Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the runtime issues found during end-to-end review: environment-dependent backend test, stale local auth schema, slow market analytics endpoints, and agent service local startup/security documentation.

**Architecture:** Keep changes scoped and reversible. Test isolation belongs in tests, DB schema drift is handled through existing Alembic migrations, and market analytics is improved in the API layer with a small TTL cache plus a single aggregate query. Agent service runtime behavior remains secure by default, with local development setup documented explicitly.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, pytest, Next.js frontend proxy, Uvicorn.

---

## File Structure

- Modify `backend/tests/test_agent_graph_core.py`
  - Make the graph test independent from the developer machine's PostgreSQL state by monkeypatching readiness.
- Execute schema repair for the current local DB
  - Prefer `cd backend; alembic upgrade head` when the local `alembic_version` is in the repo's migration chain.
  - If Alembic is blocked by a local revision not present in this repo, apply the existing migration's non-destructive DDL manually: `ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE`.
- Modify `backend/app/routers/market.py`
  - Replace sequential full-table aggregate queries in `/market/stats` with a TTL-cached single aggregate query.
  - Add cache-control headers for market analytics endpoints that are expensive but acceptable to serve slightly stale.
- Modify `backend/tests/test_market_stats.py`
  - Add a regression test proving repeated calls to `/market/stats` use the cache rather than hitting the DB every time.
- Modify `README.md`
  - Correct local agent-service command to run from repo root with `PYTHONPATH` including `backend`.
  - Document `AGENT_ALLOW_DEV_INTERNAL_KEY=true` for local-only dev key usage.

---

## Task 1: Stabilize Agent Graph Readiness Test

**Files:**
- Modify: `backend/tests/test_agent_graph_core.py`

- [ ] **Step 1: Use the existing failing test as RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_agent_graph_core.py::test_agent_graph_returns_trace_summary_without_llm_key -q
```

Expected before fix:

```text
FAILED ... assert 'ready' == 'unknown'
```

- [ ] **Step 2: Patch readiness in the test**

In `test_agent_graph_returns_trace_summary_without_llm_key`, add:

```python
    async def fake_readiness_snapshot():
        return {
            "listings": {"status": "unknown", "parent_count": 0, "chunk_count": 0},
            "projects": {"status": "unknown", "parent_count": 0, "chunk_count": 0},
            "news": {"status": "unknown", "parent_count": 0, "chunk_count": 0},
            "legal": {"status": "unknown", "parent_count": 0, "chunk_count": 0},
        }

    monkeypatch.setattr(nodes, "build_readiness_snapshot", fake_readiness_snapshot)
```

- [ ] **Step 3: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_agent_graph_core.py::test_agent_graph_returns_trace_summary_without_llm_key -q
```

Expected:

```text
1 passed
```

## Task 2: Apply Existing Auth Schema Migration

**Files:**
- No source edit required for the local schema fix.
- Existing migration source: `backend/alembic/versions/20260603_0011_add_user_is_admin.py`

- [ ] **Step 1: Reproduce auth schema failure**

Run a local query or auth smoke test.

Expected before migration:

```text
UndefinedColumnError: column users.is_admin does not exist
```

- [ ] **Step 2: Apply migration when Alembic chain is valid**

Run:

```powershell
cd backend
..\ .venv\Scripts\python.exe -m alembic upgrade head
```

Use the actual command without the space:

```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
```

If this fails with:

```text
Can't locate revision identified by '20260801_0009'
```

do not reset or stamp the database. Apply the missing column directly:

```powershell
@'
import sys, asyncio
sys.path.insert(0, 'backend')
from sqlalchemy import text
from app.database import async_session

async def main():
    async with async_session() as session:
        await session.execute(text('ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE'))
        await session.commit()

asyncio.run(main())
'@ | .\.venv\Scripts\python.exe -
```

- [ ] **Step 3: Verify auth endpoint no longer 500s**

Run:

```powershell
$body = @{ email = "no-such-user@example.com"; password = "bad-password" } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8000/api/v1/auth/login" -Method Post -ContentType "application/json" -Body $body
```

Expected after migration:

```text
HTTP 401 Invalid email or password
```

## Task 3: Cache and Consolidate Market Stats

**Files:**
- Modify: `backend/app/routers/market.py`
- Modify: `backend/tests/test_market_stats.py`

- [ ] **Step 1: Write RED cache regression test**

Add a test in `backend/tests/test_market_stats.py` that calls `get_market_stats()` twice with a fake DB session and asserts only one `execute()` call occurs.

Target test code:

```python
@pytest.mark.asyncio
async def test_market_stats_uses_ttl_cache(monkeypatch):
    from app.routers import market

    market._market_stats_cache.clear()

    execute_calls = 0

    class FakeResult:
        def one(self):
            return (10, 3.5, 70.0, 7, 3, 2, 5)

    class FakeSession:
        async def execute(self, statement):
            nonlocal execute_calls
            execute_calls += 1
            return FakeResult()

    first = await market.get_market_stats(db=FakeSession())
    second = await market.get_market_stats(db=FakeSession())

    assert first == second
    assert execute_calls == 1
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_market_stats.py::test_market_stats_uses_ttl_cache -q
```

Expected before implementation:

```text
FAILED ... AttributeError: module 'app.routers.market' has no attribute '_market_stats_cache'
```

- [ ] **Step 3: Implement minimal cache and single aggregate query**

In `backend/app/routers/market.py`:

```python
import time
from typing import Any

MARKET_STATS_TTL_SECONDS = 300
_market_stats_cache: dict[str, Any] = {}


def _cached_market_stats() -> dict[str, Any] | None:
    expires_at = _market_stats_cache.get("expires_at", 0.0)
    if expires_at > time.monotonic():
        return _market_stats_cache.get("data")
    return None


def _store_market_stats(data: dict[str, Any]) -> dict[str, Any]:
    _market_stats_cache["data"] = data
    _market_stats_cache["expires_at"] = time.monotonic() + MARKET_STATS_TTL_SECONDS
    return data
```

Then replace `/market/stats` body with one aggregate query using `count().filter(...)`, `avg(...)`, and `count(distinct(...))`, and return `_store_market_stats(data)`.

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_market_stats.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Smoke-test endpoint latency twice**

Run:

```powershell
curl.exe --max-time 140 -s -w "`nHTTP=%{http_code} TIME=%{time_total}" "http://localhost:8000/api/v1/market/stats"
curl.exe --max-time 10 -s -w "`nHTTP=%{http_code} TIME=%{time_total}" "http://localhost:8000/api/v1/market/stats"
```

Expected:

```text
First request: HTTP=200, may be slower while filling cache.
Second request: HTTP=200, fast enough for frontend proxy.
```

## Task 4: Fix Agent Service Local Setup Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the current failure**

The old local command is:

```powershell
cd agent_service
uvicorn main:app --reload --host 0.0.0.0 --port 8100
```

It fails locally because `agent_service.tools.retrieval` imports `app.services.rag.hybrid_search`, and `app` lives under `backend/`.

- [ ] **Step 2: Replace with repo-root command**

Use:

```powershell
$env:PYTHONPATH="$PWD;$PWD\backend"
$env:AGENT_ALLOW_DEV_INTERNAL_KEY="true"
uvicorn agent_service.main:app --reload --host 0.0.0.0 --port 8100
```

Explain that `AGENT_ALLOW_DEV_INTERNAL_KEY=true` is local-only; production must use a non-default `AGENT_INTERNAL_KEY`.

- [ ] **Step 3: Verify agent health**

Run:

```powershell
$env:PYTHONPATH="$PWD;$PWD\backend"
$env:AGENT_ALLOW_DEV_INTERNAL_KEY="true"
.\.venv\Scripts\python.exe -m uvicorn agent_service.main:app --host 0.0.0.0 --port 8100
curl.exe -H "X-Internal-Agent-Key: dev-agent-internal-key" http://localhost:8100/internal/agent/health
```

Expected:

```json
{"status":"ok","service":"agent-service","graph_version":"agent-graph-v1"}
```

## Task 5: Full Verification and Review

**Files:**
- Review all touched files with `git diff`.

- [ ] **Step 1: Run focused backend tests**

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_agent_graph_core.py::test_agent_graph_returns_trace_summary_without_llm_key backend\tests\test_market_stats.py -q
```

- [ ] **Step 2: Run full backend tests**

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
```

- [ ] **Step 3: Run frontend verification**

```powershell
cd frontend
npm.cmd run lint
npm.cmd run build
```

- [ ] **Step 4: Smoke-test runtime**

```powershell
curl.exe --max-time 10 -s -w "health=%{http_code}" http://localhost:8000/api/v1/health
curl.exe --max-time 10 -s -w "market_stats=%{http_code} time=%{time_total}" http://localhost:8000/api/v1/market/stats
curl.exe --max-time 20 -s -w "frontend=%{http_code}" http://localhost:3000/
```

- [ ] **Step 5: Review diff**

Run:

```powershell
git diff -- backend/tests/test_agent_graph_core.py backend/app/routers/market.py backend/tests/test_market_stats.py README.md docs/superpowers/plans/2026-06-07-runtime-review-fixes.md
```

Confirm:

- Tests are deterministic.
- Market cache is simple and bounded.
- Security defaults are not weakened.
- README local instructions match actual import path requirements.
