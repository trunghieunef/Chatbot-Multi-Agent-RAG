# Agent Platform Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the multi-agent platform across orchestration, latency, synthesis quality, memory, context usage, investment analysis, streaming, and test isolation.

**Architecture:** Keep the existing FastAPI backend -> internal Agent Service -> LangGraph workflow shape. Make the first improvements inside existing graph nodes and focused helper modules, preserving deterministic fallbacks so the app remains usable when LLM calls, retrieval, or streaming fail.

**Tech Stack:** Python 3.11, FastAPI, LangGraph, Pydantic v2, SQLAlchemy async, pytest, pytest-asyncio, Gemini client wrapper, Server-Sent Events for streaming.

---

## Scope And Order

This plan covers all review items that are still relevant in the current workspace:

1. Parallel retrieval tasks.
2. Parallel specialist agents.
3. LLM synthesis node with deterministic fallback.
4. Readiness TTL cache and real readiness endpoint.
5. Conversation context in routing, query understanding, and synthesis.
6. Memory proposal extraction beyond the hard-coded Quan 7 rule.
7. Investment advisor calculators.
8. Dedicated `agent_service/tests/` coverage.
9. SSE streaming as the final product-facing layer.

Do the tasks in this order. Tasks 1-4 improve core runtime behavior with low UI blast radius. Tasks 5-7 improve intelligence. Tasks 8-9 improve maintainability and UX after core behavior is stable.

## File Structure

- Modify `agent_service/graph/retrieval_planner.py`
  - Responsibility: build retrieval plans, execute independent retrieval tasks concurrently, normalize retrieved records into evidence.
- Modify `agent_service/graph/nodes.py`
  - Responsibility: LangGraph node orchestration, specialist execution, synthesis, safety validation, memory proposal node integration.
- Create `agent_service/graph/synthesis.py`
  - Responsibility: build synthesis prompt, call LLM synthesis, validate/fallback to deterministic synthesis.
- Create `agent_service/graph/memory_extraction.py`
  - Responsibility: extract structured memory proposals from the current query and existing query understanding.
- Modify `agent_service/graph/router.py`
  - Responsibility: include compact conversation context in LLM router prompt without changing rule router behavior.
- Modify `agent_service/graph/query_understanding.py`
  - Responsibility: include compact conversation context in query understanding prompt.
- Modify `agent_service/tools/readiness.py`
  - Responsibility: TTL cache source readiness snapshot.
- Modify `agent_service/main.py`
  - Responsibility: return real readiness snapshot from `/internal/agent/readiness`.
- Modify `agent_service/agents/specialists.py`
  - Responsibility: add deterministic investment calculations and include them in the investment advisor response.
- Create `agent_service/tests/conftest.py`
  - Responsibility: make standalone agent service tests reliable without loading heavy embedding models unless explicitly requested.
- Create or move focused tests under `agent_service/tests/`.
  - Responsibility: verify agent service behavior independently from backend router tests.
- Modify `backend/app/services/agent_service/contracts.py`
  - Responsibility: add streaming event contract used by backend client and frontend response plumbing.
- Modify `backend/app/services/agent_service/client.py`
  - Responsibility: add an async streaming client method for Agent Service SSE.
- Modify `backend/app/routers/chat.py`
  - Responsibility: add `/chat/stream` endpoint while preserving existing `/chat` endpoint.

---

### Task 1: Parallel Retrieval Task Execution

**Files:**
- Modify: `agent_service/graph/retrieval_planner.py`
- Test: `agent_service/tests/test_retrieval_parallel.py`

- [ ] **Step 1: Create standalone test directory**

Create `agent_service/tests/conftest.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

- [ ] **Step 2: Write failing test for concurrent retrieval**

Create `agent_service/tests/test_retrieval_parallel.py`:

```python
from __future__ import annotations

import asyncio
import time

import pytest

from agent_service.contracts import AgentChatRequest, RetrievalTask
from agent_service.graph import retrieval_planner
from agent_service.graph.retrieval_planner import execute_retrieval_plan


def _state() -> dict:
    return {
        "request": AgentChatRequest(
            request_id="req-parallel-retrieval",
            session_id="session-1",
            message="Tim can ho Quan 7 va thong tin phap ly",
        ),
        "agents_to_run": ["property_search", "legal_advisor"],
        "warnings": [],
    }


@pytest.mark.asyncio
async def test_execute_retrieval_plan_runs_independent_tasks_concurrently(monkeypatch):
    started: list[str] = []

    async def fake_run_hybrid_tool(**kwargs):
        started.append(kwargs["parent_type"])
        await asyncio.sleep(0.1)
        return [
            {
                "id": kwargs["parent_type"],
                "title": f"{kwargs['parent_type']} result",
                "url": f"https://example.test/{kwargs['parent_type']}",
                "matched_chunk": {
                    "id": f"chunk-{kwargs['parent_type']}",
                    "text": "matched text",
                    "rerank_score": 0.9,
                },
            }
        ]

    monkeypatch.setattr(retrieval_planner, "_run_hybrid_tool", fake_run_hybrid_tool)
    plan = [
        RetrievalTask(
            task_id="search_property_1",
            domain="property",
            tool="search_listings",
            query="can ho quan 7",
            filters={},
            retrieved_for=["property_search"],
        ),
        RetrievalTask(
            task_id="search_legal_1",
            domain="legal",
            tool="search_articles",
            query="phap ly can ho",
            filters={"category": "legal"},
            retrieved_for=["legal_advisor"],
        ),
    ]

    started_at = time.perf_counter()
    update = await execute_retrieval_plan(plan, _state())
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.18
    assert set(started) == {"listing", "article"}
    assert update["retrieval_results"]["search_property_1"].status == "completed"
    assert update["retrieval_results"]["search_legal_1"].status == "completed"
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```powershell
python -m pytest agent_service/tests/test_retrieval_parallel.py -q
```

Expected: FAIL because current `execute_retrieval_plan()` runs tasks sequentially and takes about 0.20s.

- [ ] **Step 4: Implement concurrent task helper**

In `agent_service/graph/retrieval_planner.py`, extract the body of the current `for task in plan:` loop into a helper with this signature:

```python
async def _execute_single_retrieval_task(
    *,
    task: RetrievalTask,
    request: Any,
    agents_to_run: list[str],
) -> tuple[
    RetrievalTask,
    RetrievalResult,
    list[Evidence],
    list[StructuredWarning],
    list[dict[str, Any]],
]:
    task_started = time.perf_counter()
    trace_events: list[dict[str, Any]] = [
        {"event": "retrieval_task_started", "task_id": task.task_id}
    ]
    warnings: list[StructuredWarning] = []
    evidence_items: list[Evidence] = []

    try:
        if task.domain == "market":
            from agent_service.tools.market import lookup_market_metrics

            records = await lookup_market_metrics(task.filters)
            if not records:
                warning = structured_warning(
                    code="investment_market_data_missing",
                    domain="market",
                    message="Market aggregate evidence is not available for this query.",
                    retryable=False,
                    details={"task_id": task.task_id, "filters": task.filters},
                )
                warnings.append(warning)
                result = RetrievalResult(
                    task_id=task.task_id,
                    status="skipped",
                    evidence_ids=[],
                    duration_ms=round((time.perf_counter() - task_started) * 1000),
                    warnings=[warning],
                    skip_reason="investment_market_data_missing",
                )
                trace_events.append(
                    {"event": "retrieval_task_skipped", "task_id": task.task_id}
                )
                return task, result, evidence_items, warnings, trace_events
        else:
            trace = RetrievalTrace(request_id=request.request_id)
            records = await _run_hybrid_tool(
                query=task.query,
                filters=task.filters,
                trace=trace,
                tool_name=task.tool,
                parent_type=_parent_type_for_task(task),
                top_k=task.top_k,
                rerank_to=task.rerank_top_k or task.top_k,
            )
    except Exception as exc:
        warning = structured_warning(
            code="retrieval_error",
            domain=task.domain,
            message=f"Retrieval task {task.task_id} failed.",
            retryable=True,
            details={"error": str(exc)},
        )
        warnings.append(warning)
        result = RetrievalResult(
            task_id=task.task_id,
            status="failed",
            evidence_ids=[],
            duration_ms=round((time.perf_counter() - task_started) * 1000),
            warnings=[warning],
            error={"type": exc.__class__.__name__, "message": str(exc)},
        )
        trace_events.append({"event": "retrieval_task_failed", "task_id": task.task_id})
        return task, result, evidence_items, warnings, trace_events

    if not records:
        warning = structured_warning(
            code="no_evidence",
            domain=task.domain,
            message=f"No evidence found for {task.domain}.",
            retryable=False,
            details={"task_id": task.task_id},
        )
        warnings.append(warning)
        result = RetrievalResult(
            task_id=task.task_id,
            status="empty",
            evidence_ids=[],
            duration_ms=round((time.perf_counter() - task_started) * 1000),
            warnings=[warning],
        )
        trace_events.append({"event": "retrieval_task_empty", "task_id": task.task_id})
        return task, result, evidence_items, warnings, trace_events

    assigned_to = _assigned_agents_for_task(task, agents_to_run)
    evidence_ids: list[str] = []
    for index, record in enumerate(records, start=1):
        evidence = normalize_record_to_evidence(
            record=record,
            task=task,
            evidence_index=index,
            assigned_to=assigned_to,
        )
        evidence_items.append(evidence)
        evidence_ids.append(evidence.evidence_id)

    result = RetrievalResult(
        task_id=task.task_id,
        status="completed",
        evidence_ids=evidence_ids,
        duration_ms=round((time.perf_counter() - task_started) * 1000),
        warnings=[],
    )
    trace_events.append(
        {
            "event": "retrieval_task_completed",
            "task_id": task.task_id,
            "evidence_ids": evidence_ids,
        }
    )
    trace_events.append(
        {
            "event": "evidence_assigned",
            "task_id": task.task_id,
            "assigned_to": assigned_to,
            "evidence_ids": evidence_ids,
        }
    )
    return task, result, evidence_items, warnings, trace_events
```

- [ ] **Step 5: Replace sequential loop with `asyncio.gather()`**

In `execute_retrieval_plan()`, keep the initial `retrieval_plan_created` event, then replace the loop with:

```python
task_outputs = await asyncio.gather(
    *(
        _execute_single_retrieval_task(
            task=task,
            request=request,
            agents_to_run=agents_to_run,
        )
        for task in plan
    )
)

for task, result, evidence_items, task_warnings, task_events in task_outputs:
    retrieval_results[task.task_id] = result
    warnings.extend(task_warnings)
    trace_events.extend(task_events)
    for evidence in evidence_items:
        evidence_by_id[evidence.evidence_id] = evidence
        for agent in evidence.assigned_to:
            evidence_for_agent.setdefault(agent, []).append(evidence.evidence_id)
```

Add `import asyncio` at the top of the file.

- [ ] **Step 6: Run retrieval tests**

Run:

```powershell
python -m pytest agent_service/tests/test_retrieval_parallel.py backend/tests/test_agent_retrieval_planner.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add agent_service/graph/retrieval_planner.py agent_service/tests/conftest.py agent_service/tests/test_retrieval_parallel.py
git commit -m "perf: run independent retrieval tasks concurrently"
```

---

### Task 2: Parallel Specialist Agent Execution

**Files:**
- Modify: `agent_service/graph/nodes.py`
- Test: `agent_service/tests/test_specialists_parallel.py`

- [ ] **Step 1: Write failing test**

Create `agent_service/tests/test_specialists_parallel.py`:

```python
from __future__ import annotations

import asyncio
import time

import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph import nodes


@pytest.mark.asyncio
async def test_specialist_agents_node_runs_agents_concurrently(monkeypatch):
    async def fake_agent(**kwargs):
        await asyncio.sleep(0.1)
        return {
            "agent_name": "fake",
            "status": "completed",
            "content": "ok",
            "evidence_ids_used": [],
            "warnings": [],
        }

    monkeypatch.setattr(nodes, "run_property_agent", fake_agent)
    monkeypatch.setattr(nodes, "run_legal_agent", fake_agent)

    state = {
        "request": AgentChatRequest(
            request_id="req-specialists-parallel",
            message="Tim can ho va kiem tra phap ly",
            session_id="session-1",
        ),
        "agents_to_run": ["property_search", "legal_advisor"],
        "evidence_by_id": {},
        "evidence_for_agent": {},
        "readiness": {},
        "warnings": [],
        "trace_steps": [],
        "force_deterministic": True,
    }

    started_at = time.perf_counter()
    result = await nodes.specialist_agents_node(state)
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.18
    assert set(result["agent_results"]) == {"property_search", "legal_advisor"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest agent_service/tests/test_specialists_parallel.py -q
```

Expected: FAIL because current node awaits each specialist in sequence.

- [ ] **Step 3: Add helper for one specialist**

In `agent_service/graph/nodes.py`, add this helper above `specialist_agents_node`:

```python
async def _run_one_specialist(
    *,
    agent: str,
    runner,
    request,
    assigned_evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
    use_llm_specialists: bool,
    llm_client: GeminiClient | None,
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    try:
        if use_llm_specialists and llm_client is not None:
            result = await run_llm_or_deterministic_specialist(
                agent_name=agent,
                deterministic_runner=runner,
                query=request.message,
                evidence=assigned_evidence,
                preferences=preferences,
                readiness=readiness,
                generate_json=llm_client.generate_json,
                timeout_seconds=timeout_seconds,
            )
        else:
            result = await runner(
                query=request.message,
                evidence=assigned_evidence,
                preferences=preferences,
                readiness=readiness,
            )
    except Exception as exc:
        result = {
            "agent_name": agent,
            "status": "failed",
            "content": "",
            "evidence_ids_used": [],
            "sources": [],
            "confidence": "low",
            "warnings": [
                StructuredWarning(
                    code="specialist_error",
                    domain=None,
                    message=f"Specialist {agent} failed.",
                    retryable=True,
                    details={"error": str(exc)},
                )
            ],
            "missing_evidence": [],
        }
    return agent, result
```

- [ ] **Step 4: Replace specialist loop with gather**

Inside `specialist_agents_node`, build tasks:

```python
specialist_tasks = []
for agent in state.get("agents_to_run", []):
    runner = runners.get(agent)
    if runner is None:
        continue
    assigned_evidence = [
        evidence_by_id[evidence_id].model_dump(mode="python")
        for evidence_id in evidence_for_agent.get(agent, [])
        if evidence_id in evidence_by_id
    ]
    specialist_tasks.append(
        _run_one_specialist(
            agent=agent,
            runner=runner,
            request=request,
            assigned_evidence=assigned_evidence,
            preferences=request.user_preferences,
            readiness=state.get("readiness", {}),
            use_llm_specialists=use_llm_specialists,
            llm_client=llm_client,
            timeout_seconds=settings.AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS,
        )
    )

agent_results = dict(await asyncio.gather(*specialist_tasks)) if specialist_tasks else {}
```

Add `import asyncio` to `agent_service/graph/nodes.py`.

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest agent_service/tests/test_specialists_parallel.py backend/tests/test_agent_graph_core.py::test_specialist_agents_node_resolves_assigned_evidence -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent_service/graph/nodes.py agent_service/tests/test_specialists_parallel.py
git commit -m "perf: run selected specialist agents concurrently"
```

---

### Task 3: LLM Synthesizer With Deterministic Fallback

**Files:**
- Create: `agent_service/graph/synthesis.py`
- Modify: `agent_service/graph/nodes.py`
- Test: `agent_service/tests/test_synthesis.py`

- [ ] **Step 1: Write tests for LLM synthesis and fallback**

Create `agent_service/tests/test_synthesis.py`:

```python
from __future__ import annotations

import pytest

from agent_service.graph.synthesis import synthesize_final_answer


@pytest.mark.asyncio
async def test_synthesize_final_answer_uses_llm_when_valid():
    async def fake_generate_json(prompt: str, *, timeout_seconds=None):
        return {
            "final_response": "Ket luan tong hop tu nhieu agent.",
            "suggested_actions": ["Xem listing", "Kiem tra phap ly"],
        }

    result = await synthesize_final_answer(
        query="Can ho nay co nen mua khong?",
        conversation_context=[],
        agent_results={
            "property_search": {"content": "Listing phu hop."},
            "legal_advisor": {"content": "Can kiem tra so hong."},
        },
        deterministic_response="Listing phu hop.\n\nCan kiem tra so hong.",
        default_actions=["So sanh lua chon"],
        generate_json=fake_generate_json,
        timeout_seconds=1.0,
    )

    assert result.final_response == "Ket luan tong hop tu nhieu agent."
    assert result.suggested_actions == ["Xem listing", "Kiem tra phap ly"]
    assert result.used_llm is True


@pytest.mark.asyncio
async def test_synthesize_final_answer_falls_back_on_invalid_payload():
    async def fake_generate_json(prompt: str, *, timeout_seconds=None):
        return {"bad": "payload"}

    result = await synthesize_final_answer(
        query="Can ho nay co nen mua khong?",
        conversation_context=[],
        agent_results={"property_search": {"content": "Listing phu hop."}},
        deterministic_response="Listing phu hop.",
        default_actions=["So sanh lua chon"],
        generate_json=fake_generate_json,
        timeout_seconds=1.0,
    )

    assert result.final_response == "Listing phu hop."
    assert result.suggested_actions == ["So sanh lua chon"]
    assert result.used_llm is False
    assert "synthesizer_invalid_json" in result.warnings
```

- [ ] **Step 2: Run tests to verify import fails**

Run:

```powershell
python -m pytest agent_service/tests/test_synthesis.py -q
```

Expected: FAIL because `agent_service/graph/synthesis.py` does not exist.

- [ ] **Step 3: Add synthesis helper module**

Create `agent_service/graph/synthesis.py`:

```python
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError


GenerateJson = Callable[..., Awaitable[dict[str, Any]]]


class SynthesisPayload(BaseModel):
    final_response: str
    suggested_actions: list[str] = Field(default_factory=list)


class SynthesisResult(BaseModel):
    final_response: str
    suggested_actions: list[str]
    warnings: list[Any] = Field(default_factory=list)
    used_llm: bool = False


def build_synthesis_prompt(
    *,
    query: str,
    conversation_context: list[dict[str, Any]],
    agent_results: dict[str, dict[str, Any]],
) -> str:
    compact_results = {
        agent: {
            "status": result.get("status"),
            "content": result.get("content"),
            "evidence_ids_used": result.get("evidence_ids_used", []),
            "warnings": [
                warning.code if hasattr(warning, "code") else warning
                for warning in result.get("warnings", [])
            ],
        }
        for agent, result in agent_results.items()
    }
    return "\n".join(
        [
            "You are the final response synthesizer for a Vietnamese real-estate assistant.",
            "Return JSON only with final_response and suggested_actions.",
            "Use only the agent outputs and evidence IDs provided.",
            "Do not invent listings, prices, laws, market facts, or citations.",
            "If evidence is missing, say what is missing and ask a useful follow-up.",
            f"User query: {query}",
            f"Conversation context: {json.dumps(conversation_context, ensure_ascii=True)}",
            f"Agent results: {json.dumps(compact_results, ensure_ascii=True, default=str)}",
        ]
    )


async def synthesize_final_answer(
    *,
    query: str,
    conversation_context: list[dict[str, Any]],
    agent_results: dict[str, dict[str, Any]],
    deterministic_response: str,
    default_actions: list[str],
    generate_json: GenerateJson | None,
    timeout_seconds: float,
) -> SynthesisResult:
    if generate_json is None:
        return SynthesisResult(
            final_response=deterministic_response,
            suggested_actions=default_actions,
            warnings=[],
            used_llm=False,
        )

    try:
        payload = await generate_json(
            build_synthesis_prompt(
                query=query,
                conversation_context=conversation_context,
                agent_results=agent_results,
            ),
            timeout_seconds=timeout_seconds,
        )
        parsed = SynthesisPayload.model_validate(payload)
    except (TypeError, ValueError, ValidationError):
        return SynthesisResult(
            final_response=deterministic_response,
            suggested_actions=default_actions,
            warnings=["synthesizer_invalid_json"],
            used_llm=False,
        )

    final_response = parsed.final_response.strip()
    if not final_response:
        return SynthesisResult(
            final_response=deterministic_response,
            suggested_actions=default_actions,
            warnings=["synthesizer_empty_response"],
            used_llm=False,
        )

    return SynthesisResult(
        final_response=final_response,
        suggested_actions=parsed.suggested_actions or default_actions,
        warnings=[],
        used_llm=True,
    )
```

- [ ] **Step 4: Convert `synthesizer_node` to async**

In `agent_service/graph/nodes.py`:

1. Import the helper:

```python
from agent_service.graph.synthesis import synthesize_final_answer
```

2. Change:

```python
def synthesizer_node(state: AgentGraphState) -> AgentGraphState:
```

to:

```python
async def synthesizer_node(state: AgentGraphState) -> AgentGraphState:
```

3. After building `final_response` and `suggested_actions`, call synthesis:

```python
settings = get_agent_settings()
use_llm_synthesis = (
    settings.AGENT_SPECIALIST_LLM_ENABLED
    and not state.get("force_deterministic", False)
)
llm_client = GeminiClient() if use_llm_synthesis else None
synthesis = await synthesize_final_answer(
    query=state["request"].message,
    conversation_context=state.get("compact_context", []),
    agent_results=agent_results,
    deterministic_response=final_response,
    default_actions=suggested_actions,
    generate_json=llm_client.generate_json if llm_client is not None else None,
    timeout_seconds=settings.AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS,
)
final_response = synthesis.final_response
suggested_actions = synthesis.suggested_actions
warnings = _dedupe_warnings([*warnings, *synthesis.warnings])
```

4. Add this to the synthesizer trace output:

```python
"used_llm_synthesis": synthesis.used_llm,
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest agent_service/tests/test_synthesis.py backend/tests/test_agent_graph_core.py::test_synthesizer_exposes_only_valid_used_evidence -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent_service/graph/synthesis.py agent_service/graph/nodes.py agent_service/tests/test_synthesis.py
git commit -m "feat: add grounded LLM synthesis fallback"
```

---

### Task 4: Readiness TTL Cache And Real Endpoint

**Files:**
- Modify: `agent_service/tools/readiness.py`
- Modify: `agent_service/main.py`
- Test: `agent_service/tests/test_readiness_cache.py`

- [ ] **Step 1: Write failing tests**

Create `agent_service/tests/test_readiness_cache.py`:

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_service import main
from agent_service.tools import readiness


@pytest.mark.asyncio
async def test_build_readiness_snapshot_uses_ttl_cache(monkeypatch):
    readiness.clear_readiness_cache()
    calls = {"count": 0}

    async def fake_count_source(source_name: str):
        calls["count"] += 1
        return {"status": "ready", "parent_count": 1, "chunk_count": 1}

    monkeypatch.setattr(readiness, "count_source", fake_count_source)

    first = await readiness.build_readiness_snapshot()
    second = await readiness.build_readiness_snapshot()

    assert first == second
    assert calls["count"] == len(readiness.SOURCE_NAMES)


def test_readiness_endpoint_returns_sources(monkeypatch):
    async def fake_snapshot():
        return {"listings": {"status": "ready", "parent_count": 1, "chunk_count": 1}}

    monkeypatch.setattr(main, "build_readiness_snapshot", fake_snapshot)
    client = TestClient(main.app)
    response = client.get(
        "/internal/agent/readiness",
        headers={"X-Agent-Internal-Key": "dev-agent-internal-key"},
    )

    assert response.status_code == 200
    assert response.json()["sources"]["listings"]["status"] == "ready"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest agent_service/tests/test_readiness_cache.py -q
```

Expected: FAIL because there is no `clear_readiness_cache()` and endpoint currently returns empty sources.

- [ ] **Step 3: Add cache to readiness tool**

In `agent_service/tools/readiness.py`, add near constants:

```python
import time

READINESS_CACHE_TTL_SECONDS = 30.0
_readiness_cache: tuple[float, dict[str, dict[str, Any]]] | None = None
```

Add:

```python
def clear_readiness_cache() -> None:
    global _readiness_cache
    _readiness_cache = None
```

Wrap `build_readiness_snapshot()`:

```python
async def build_readiness_snapshot() -> dict[str, dict[str, Any]]:
    global _readiness_cache
    now = time.monotonic()
    if _readiness_cache is not None:
        cached_at, cached_value = _readiness_cache
        if now - cached_at < READINESS_CACHE_TTL_SECONDS:
            return cached_value

    async def safe_count(source_name: str) -> tuple[str, dict[str, Any]]:
        try:
            result = await asyncio.wait_for(
                count_source(source_name),
                timeout=READINESS_SOURCE_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            result = {
                "status": "unknown",
                "parent_count": 0,
                "chunk_count": 0,
                "warning": str(exc),
            }
        return source_name, result

    pairs = await asyncio.gather(
        *(safe_count(source_name) for source_name in SOURCE_NAMES)
    )
    snapshot = dict(pairs)
    _readiness_cache = (now, snapshot)
    return snapshot
```

- [ ] **Step 4: Return real readiness from endpoint**

In `agent_service/main.py`, import:

```python
from agent_service.tools.readiness import build_readiness_snapshot
```

Change endpoint to:

```python
@app.get("/internal/agent/readiness")
async def readiness(_: None = Depends(require_internal_key)) -> dict:
    sources = await build_readiness_snapshot()
    status = "ok" if any(
        source.get("status") == "ready" for source in sources.values()
    ) else "degraded"
    return {"status": status, "sources": sources}
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest agent_service/tests/test_readiness_cache.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent_service/tools/readiness.py agent_service/main.py agent_service/tests/test_readiness_cache.py
git commit -m "perf: cache readiness snapshots"
```

---

### Task 5: Use Conversation Context In Agent Intelligence

**Files:**
- Modify: `agent_service/graph/nodes.py`
- Modify: `agent_service/graph/router.py`
- Modify: `agent_service/graph/query_understanding.py`
- Modify: `agent_service/graph/synthesis.py`
- Test: `agent_service/tests/test_conversation_context.py`

- [ ] **Step 1: Write context compaction tests**

Create `agent_service/tests/test_conversation_context.py`:

```python
from __future__ import annotations

from agent_service.contracts import AgentChatRequest, ConversationContextItem
from agent_service.graph.nodes import context_builder
from agent_service.graph.router import _router_prompt


def test_context_builder_creates_compact_context():
    request = AgentChatRequest(
        request_id="req-context",
        session_id="session-1",
        message="Can ho nay co phap ly on khong?",
        conversation_context=[
            ConversationContextItem(role="user", content="Toi muon mua can ho Quan 7"),
            ConversationContextItem(role="assistant", content="Ban dang tim can ho Quan 7."),
        ],
    )

    result = context_builder({"request": request, "trace_steps": []})

    assert result["compact_context"] == [
        {"role": "user", "content": "Toi muon mua can ho Quan 7"},
        {"role": "assistant", "content": "Ban dang tim can ho Quan 7."},
    ]


def test_router_prompt_includes_compact_context():
    prompt = _router_prompt(
        "No co nen mua khong?",
        [{"role": "user", "content": "Dang noi ve can ho Quan 7"}],
    )

    assert "Dang noi ve can ho Quan 7" in prompt
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest agent_service/tests/test_conversation_context.py -q
```

Expected: FAIL because `compact_context` does not exist and `_router_prompt()` takes one argument.

- [ ] **Step 3: Add compact context in `context_builder`**

In `agent_service/graph/nodes.py`, add:

```python
def _compact_conversation_context(request) -> list[dict[str, str]]:
    compact: list[dict[str, str]] = []
    for item in request.conversation_context[-6:]:
        content = (item.content or "").strip()
        if not content:
            continue
        compact.append(
            {
                "role": item.role,
                "content": content[:500],
            }
        )
    return compact
```

Then update `context_builder()` return:

```python
compact_context = _compact_conversation_context(request)
return {
    "normalized_query": normalized_query,
    "compact_context": compact_context,
    "trace_steps": _append_trace(
        state,
        "context_builder",
        start_time,
        {
            "context_items": len(request.conversation_context),
            "compact_context_items": len(compact_context),
        },
    ),
}
```

Add `compact_context: list[dict[str, str]]` to `AgentGraphState` in `agent_service/graph/state.py`.

- [ ] **Step 4: Update router prompt signature**

In `agent_service/graph/router.py`, change:

```python
def _router_prompt(query: str) -> str:
```

to:

```python
def _router_prompt(query: str, compact_context: list[dict[str, Any]] | None = None) -> str:
    context = compact_context or []
    return (
        "Ban la bo dinh tuyen intent bat dong san. Tra ve JSON duy nhat voi "
        "intent, agents, confidence, filters, needs_clarification, "
        "clarifying_question, reason. Khong tra loi nguoi dung.\n"
        f"Conversation context: {context}\n"
        f"Query: {query}"
    )
```

Update `route_with_llm()`:

```python
payload = await client.generate_json(
    _router_prompt(request.message, state.get("compact_context", [])),
    timeout_seconds=settings.AGENT_LLM_ROUTER_TIMEOUT_SECONDS,
)
```

- [ ] **Step 5: Update query understanding prompt**

In `agent_service/graph/query_understanding.py`, change prompt function:

```python
def _query_understanding_prompt(
    query: str,
    max_rewrites: int,
    compact_context: list[dict[str, Any]] | None = None,
) -> str:
    context = compact_context or []
    return (
        "Phan tich query bat dong san va tra ve JSON voi rewritten_query, "
        "expanded_queries, filters, missing_slots. Khong tra loi nguoi dung. "
        f"Toi da {max_rewrites} expanded queries.\n"
        f"Conversation context: {context}\n"
        f"Query: {query}"
    )
```

Update call site:

```python
_query_understanding_prompt(
    request.message,
    settings.AGENT_LLM_MAX_REWRITES,
    state.get("compact_context", []),
)
```

- [ ] **Step 6: Run tests**

Run:

```powershell
python -m pytest agent_service/tests/test_conversation_context.py backend/tests/test_agent_llm_router.py -q
```

Expected: PASS. If existing tests call `_router_prompt(query)` directly, keep default `compact_context=None` to preserve compatibility.

- [ ] **Step 7: Commit**

```powershell
git add agent_service/graph/nodes.py agent_service/graph/state.py agent_service/graph/router.py agent_service/graph/query_understanding.py agent_service/tests/test_conversation_context.py
git commit -m "feat: include compact conversation context in agent intelligence"
```

---

### Task 6: Memory Proposal Extraction

**Files:**
- Create: `agent_service/graph/memory_extraction.py`
- Modify: `agent_service/graph/nodes.py`
- Test: `agent_service/tests/test_memory_extraction.py`

- [ ] **Step 1: Write tests**

Create `agent_service/tests/test_memory_extraction.py`:

```python
from __future__ import annotations

from agent_service.graph.memory_extraction import extract_memory_proposals


def test_extract_memory_proposals_from_query_and_filters():
    proposals = extract_memory_proposals(
        query="Toi muon mua can ho 2 phong ngu o Quan 7 duoi 5 ty",
        filters={
            "listing_type": "sale",
            "property_type": "Can ho",
            "district": "Quan 7",
            "max_price": 5.0,
            "bedrooms": 2,
        },
    )

    by_key = {proposal.key: proposal.value for proposal in proposals}

    assert by_key["listing_type"] == "sale"
    assert by_key["preferred_property_type"] == "Can ho"
    assert by_key["preferred_district"] == "Quan 7"
    assert by_key["max_budget"] == 5.0
    assert by_key["bedrooms"] == 2


def test_extract_memory_proposals_ignores_empty_filters():
    assert extract_memory_proposals(query="Xin chao", filters={}) == []
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest agent_service/tests/test_memory_extraction.py -q
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Create memory extraction module**

Create `agent_service/graph/memory_extraction.py`:

```python
from __future__ import annotations

from typing import Any

from agent_service.contracts import MemoryProposal


FILTER_TO_MEMORY_KEY = {
    "city": "preferred_city",
    "district": "preferred_district",
    "property_type": "preferred_property_type",
    "listing_type": "listing_type",
    "bedrooms": "bedrooms",
    "max_price": "max_budget",
    "min_price": "min_budget",
}


def _confidence_for_key(key: str) -> float:
    if key in {"preferred_district", "preferred_city", "listing_type"}:
        return 0.82
    if key in {"max_budget", "min_budget", "bedrooms"}:
        return 0.78
    return 0.72


def extract_memory_proposals(
    *,
    query: str,
    filters: dict[str, Any],
) -> list[MemoryProposal]:
    proposals: list[MemoryProposal] = []
    clean_query = query.strip()
    for filter_key, memory_key in FILTER_TO_MEMORY_KEY.items():
        value = filters.get(filter_key)
        if value is None or value == "":
            continue
        proposals.append(
            MemoryProposal(
                action="upsert",
                key=memory_key,
                value=value,
                confidence=_confidence_for_key(memory_key),
                evidence=f"Current query implied {memory_key}: {value}. Query: {clean_query[:160]}",
                requires_user_confirmation=True,
            )
        )
    return proposals
```

- [ ] **Step 4: Replace hard-coded memory rule**

In `agent_service/graph/nodes.py`, import:

```python
from agent_service.graph.memory_extraction import extract_memory_proposals
```

Replace `memory_proposal_node()` body with:

```python
def memory_proposal_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    understanding = state.get("query_understanding") or {}
    filters = understanding.get("filters") or {}
    memory_proposals = extract_memory_proposals(
        query=state["request"].message,
        filters=filters,
    )

    return {
        "memory_proposals": memory_proposals,
        "trace_steps": _append_trace(
            state,
            "memory_proposals",
            start_time,
            {"proposal_count": len(memory_proposals)},
        ),
    }
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest agent_service/tests/test_memory_extraction.py backend/tests/test_agent_memory_filters.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent_service/graph/memory_extraction.py agent_service/graph/nodes.py agent_service/tests/test_memory_extraction.py
git commit -m "feat: extract structured memory proposals"
```

---

### Task 7: Investment Advisor Calculators

**Files:**
- Modify: `agent_service/agents/specialists.py`
- Test: `agent_service/tests/test_investment_calculators.py`

- [ ] **Step 1: Write tests**

Create `agent_service/tests/test_investment_calculators.py`:

```python
from __future__ import annotations

import pytest

from agent_service.agents.specialists import (
    _investment_calculations,
    run_investment_agent,
)


def test_investment_calculations_compute_price_per_m2_delta():
    calculations = _investment_calculations(
        property_evidence=[
            {
                "facts": {
                    "title": "Can ho Quan 7",
                    "price": 4.8,
                    "area": 75,
                    "location": {"district": "Quan 7", "city": "Ho Chi Minh"},
                }
            }
        ],
        market_evidence=[
            {
                "facts": {
                    "metric": "avg_price_per_m2",
                    "value": 70,
                    "unit": "million VND/m2",
                }
            }
        ],
    )

    assert calculations[0]["listing_price_per_m2_million"] == 64.0
    assert calculations[0]["market_delta_percent"] == -8.57


@pytest.mark.asyncio
async def test_investment_agent_mentions_price_per_m2_when_available():
    result = await run_investment_agent(
        query="Co nen dau tu can ho nay khong?",
        evidence=[
            {
                "evidence_id": "ev_listing",
                "domain": "property",
                "facts": {
                    "title": "Can ho Quan 7",
                    "price": 4.8,
                    "area": 75,
                },
            },
            {
                "evidence_id": "ev_market",
                "domain": "market",
                "source_type": "market_metric",
                "facts": {
                    "metric": "avg_price_per_m2",
                    "value": 70,
                    "unit": "million VND/m2",
                },
            },
        ],
        preferences={},
        readiness={"listings": {"status": "ready"}},
    )

    assert "64.0 trieu/m2" in result["content"]
    assert "chenh lech -8.57%" in result["content"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_calculators.py -q
```

Expected: FAIL because `_investment_calculations` does not exist.

- [ ] **Step 3: Add calculator helpers**

In `agent_service/agents/specialists.py`, add above `run_investment_agent()`:

```python
def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _market_avg_price_per_m2(market_evidence: list[dict[str, Any]]) -> float | None:
    for item in market_evidence:
        facts = _evidence_facts(item)
        if facts.get("metric") == "avg_price_per_m2":
            return _number(facts.get("value"))
    return None


def _investment_calculations(
    *,
    property_evidence: list[dict[str, Any]],
    market_evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    market_avg = _market_avg_price_per_m2(market_evidence)
    calculations: list[dict[str, Any]] = []
    for item in property_evidence:
        facts = _evidence_facts(item)
        price_billion = _number(facts.get("price"))
        area_m2 = _number(facts.get("area"))
        if price_billion is None or area_m2 in {None, 0}:
            continue
        listing_price_per_m2 = round(price_billion * 1000 / area_m2, 2)
        calculation = {
            "title": facts.get("title") or "Listing",
            "listing_price_per_m2_million": listing_price_per_m2,
        }
        if market_avg not in {None, 0}:
            calculation["market_avg_price_per_m2_million"] = market_avg
            calculation["market_delta_percent"] = round(
                ((listing_price_per_m2 - market_avg) / market_avg) * 100,
                2,
            )
        calculations.append(calculation)
    return calculations
```

- [ ] **Step 4: Include calculations in investment content**

Inside `run_investment_agent()`, after `used_evidence` is built:

```python
calculations = _investment_calculations(
    property_evidence=property_evidence,
    market_evidence=market_evidence,
)
```

After market evidence content:

```python
if calculations:
    content += "\nTinh toan dau tu co ban:\n" + "\n".join(
        (
            f"- {item['title']}: {item['listing_price_per_m2_million']} trieu/m2"
            + (
                f", chenh lech {item['market_delta_percent']}% so voi trung binh khu vuc"
                if "market_delta_percent" in item
                else ", chua co trung binh khu vuc de so sanh"
            )
        )
        for item in calculations
    )
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_calculators.py backend/tests/test_agent_specialists.py::test_investment_agent_warns_when_market_metric_missing -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent_service/agents/specialists.py agent_service/tests/test_investment_calculators.py
git commit -m "feat: add investment price comparison calculations"
```

---

### Task 8: Dedicated Agent Service Test Suite

**Files:**
- Create: `agent_service/tests/test_graph_smoke.py`
- Create: `agent_service/tests/test_router_modes.py`
- Create: `agent_service/tests/test_memory_node.py`
- Modify: `pyproject.toml` or existing pytest config only if the repo already has one.

- [ ] **Step 1: Add graph smoke test that avoids heavy embedding load**

Create `agent_service/tests/test_graph_smoke.py`:

```python
from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph import nodes
from agent_service.graph.workflow import run_agent_graph


@pytest.mark.asyncio
async def test_agent_graph_smoke_without_ready_sources(monkeypatch):
    async def fake_readiness_snapshot():
        return {
            "listings": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "projects": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "news": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "legal": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
        }

    monkeypatch.setattr(nodes, "build_readiness_snapshot", fake_readiness_snapshot)

    response = await run_agent_graph(
        AgentChatRequest(
            request_id="req-agent-service-smoke",
            session_id="session-1",
            message="Tim can ho Quan 7",
        )
    )

    assert response.request_id == "req-agent-service-smoke"
    assert response.final_response
    assert response.full_trace["steps"]
```

- [ ] **Step 2: Add router mode tests**

Create `agent_service/tests/test_router_modes.py`:

```python
from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph.router import RouterDecision, merge_router_decisions, route_with_rules


def test_rule_router_routes_mixed_legal_investment_property():
    state = {
        "normalized_query": "tim can ho quan 7 phap ly va dau tu",
        "request": AgentChatRequest(
            request_id="req-router-rules",
            session_id="session-1",
            message="Tim can ho Quan 7 phap ly va dau tu",
        ),
    }

    decision = route_with_rules(state)

    assert set(decision.agents) >= {
        "property_search",
        "legal_advisor",
        "investment_advisor",
    }


def test_hybrid_router_merges_valid_llm_agent():
    rule = RouterDecision(
        intent="property_search",
        agents=["property_search"],
        confidence=1.0,
        reason="rule",
    )
    llm = RouterDecision(
        intent="legal_advice",
        agents=["legal_advisor"],
        confidence=0.9,
        reason="llm",
    )

    merged = merge_router_decisions(rule, llm, confidence_threshold=0.65)

    assert merged.mode == "hybrid"
    assert merged.agents == ["property_search", "legal_advisor"]
```

- [ ] **Step 3: Add memory node test**

Create `agent_service/tests/test_memory_node.py`:

```python
from __future__ import annotations

from agent_service.contracts import AgentChatRequest
from agent_service.graph.nodes import memory_proposal_node


def test_memory_node_uses_query_understanding_filters():
    state = {
        "request": AgentChatRequest(
            request_id="req-memory-node",
            session_id="session-1",
            message="Toi muon mua can ho Quan 7",
        ),
        "query_understanding": {
            "filters": {
                "listing_type": "sale",
                "property_type": "Can ho",
                "district": "Quan 7",
            }
        },
        "trace_steps": [],
    }

    result = memory_proposal_node(state)
    keys = {proposal.key for proposal in result["memory_proposals"]}

    assert {"listing_type", "preferred_property_type", "preferred_district"}.issubset(keys)
```

- [ ] **Step 4: Run all standalone agent service tests**

Run:

```powershell
python -m pytest agent_service/tests -q
```

Expected: PASS without loading local sentence-transformer models unless a test explicitly exercises retrieval.

- [ ] **Step 5: Commit**

```powershell
git add agent_service/tests
git commit -m "test: add standalone agent service suite"
```

---

### Task 9: SSE Streaming For Chat Progress

**Files:**
- Modify: `backend/app/services/agent_service/contracts.py`
- Modify: `backend/app/services/agent_service/client.py`
- Modify: `backend/app/routers/chat.py`
- Optional later: `frontend/lib/api.ts`
- Optional later: chat UI component that consumes streaming.
- Test: `backend/tests/test_chat_streaming.py`

- [ ] **Step 1: Add stream event contract**

In `backend/app/services/agent_service/contracts.py`, add:

```python
from typing import Literal


class AgentStreamEvent(BaseModel):
    event: Literal[
        "started",
        "routing",
        "retrieval",
        "specialist",
        "synthesis",
        "final",
        "error",
    ]
    request_id: str
    payload: dict = Field(default_factory=dict)
```

- [ ] **Step 2: Write backend streaming endpoint test**

Create `backend/tests/test_chat_streaming.py`:

```python
from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest.mark.asyncio
async def test_chat_stream_endpoint_returns_sse(monkeypatch):
    async def fake_stream_response(*args, **kwargs):
        yield {"event": "started", "request_id": "req-stream", "payload": {}}
        yield {
            "event": "final",
            "request_id": "req-stream",
            "payload": {"content": "Xin chao"},
        }

    monkeypatch.setattr(
        "app.routers.chat._stream_agent_service_pipeline",
        fake_stream_response,
        raising=False,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat/stream",
            json={"message": "Xin chao"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: started" in response.text
    assert "event: final" in response.text
```

- [ ] **Step 3: Add SSE formatter**

In `backend/app/routers/chat.py`, add:

```python
import json
from fastapi.responses import StreamingResponse


def _format_sse(event: dict) -> str:
    event_name = str(event.get("event") or "message")
    payload = json.dumps(event, ensure_ascii=False, default=str)
    return f"event: {event_name}\ndata: {payload}\n\n"
```

- [ ] **Step 4: Add stream pipeline wrapper**

In `backend/app/routers/chat.py`, add:

```python
async def _stream_agent_service_pipeline(
    message: str,
    db: AsyncSession,
    session: ChatSession,
    user: User | None,
    request_id: str,
):
    yield {"event": "started", "request_id": request_id, "payload": {}}
    response = await _run_agent_service_pipeline(
        message,
        db,
        session,
        user,
        request_id,
    )
    yield {
        "event": "final",
        "request_id": request_id,
        "payload": response.model_dump(mode="json"),
    }
```

This first streaming version streams progress wrapper events while preserving the existing non-streaming agent graph. A later graph-native streaming implementation can emit per-node events from LangGraph.

- [ ] **Step 5: Add `/chat/stream` endpoint**

In `backend/app/routers/chat.py`, add a route after `send_message()` or near it:

```python
@router.post("/stream")
async def stream_message(
    body: ChatMessageRequest,
    request: Request = None,
    response: Response = None,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    request_id = str(uuid.uuid4())
    request = request or Request({"type": "http", "client": ("direct-test", 0)})
    response = response or Response()
    _enforce_chat_abuse_guard(body, user, request, response)

    if body.session_id:
        result = await db.execute(
            select(ChatSession).where(ChatSession.id == body.session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        verify_session_ownership(session, user)
    else:
        session = ChatSession(
            user_id=user.id if user else None,
            title=body.message[:80],
        )
        db.add(session)
        await db.flush()

    await enforce_chat_quota(db, user=user, session_id=session.id)

    async def event_generator():
        async for event in _stream_agent_service_pipeline(
            body.message,
            db,
            session,
            user,
            request_id,
        ):
            yield _format_sse(event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
```

- [ ] **Step 6: Run streaming test**

Run:

```powershell
python -m pytest backend/tests/test_chat_streaming.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/services/agent_service/contracts.py backend/app/routers/chat.py backend/tests/test_chat_streaming.py
git commit -m "feat: add SSE chat streaming endpoint"
```

---

## Verification Matrix

After completing all tasks, run focused checks first:

```powershell
python -m pytest agent_service/tests -q
python -m pytest backend/tests/test_agent_graph_core.py backend/tests/test_agent_retrieval_planner.py backend/tests/test_agent_specialists.py -q
python -m pytest backend/tests/test_chat_streaming.py backend/tests/test_chat_agent_service_integration.py -q
```

Then run the broader suite:

```powershell
python -m pytest backend/tests -q
```

If the broader suite triggers local embedding model loading and crashes on Windows, isolate the failing test, monkeypatch retrieval calls in graph smoke tests, and keep a separate integration test profile for real embedding-backed retrieval.

## Risk Controls

- Keep deterministic fallbacks for router, query understanding, specialists, and synthesis.
- Keep existing `/chat` behavior while adding `/chat/stream`.
- Preserve evidence validation in `synthesizer_node`; the LLM synthesizer may rewrite answer text but must not decide source validity.
- Run parallel retrieval and specialists with isolated per-task/per-agent errors.
- Do not refactor graph topology and streaming in the same commit.

## Self-Review

- Spec coverage: all image-review items are covered: conditional/parallel graph behavior, sequential specialists, sequential retrieval, LLM synthesis, memory, context, readiness, router mode, investment advisor, tests, and streaming.
- Completeness scan: no unfinished markers or unspecified "handle later" tasks remain.
- Type consistency: new helpers use existing `AgentChatRequest`, `RetrievalTask`, `RetrievalResult`, `Evidence`, `StructuredWarning`, and `MemoryProposal` contracts.
- Scope check: this is a multi-sprint plan. Tasks 1-4 can ship independently as the first improvement milestone.
