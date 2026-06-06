# Agent Service Grounded Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the production `agent_service` LangGraph path to real indexed pipeline data through planner-owned retrieval, evidence sharing, and source-safe synthesis.

**Architecture:** Keep `retrieval_planner_node` as one LangGraph node, but move its internals into testable `build_retrieval_plan()` and `execute_retrieval_plan()` functions. Store evidence once in `evidence_by_id`, assign IDs via `evidence_for_agent`, and let specialists return validated `evidence_ids_used`; final sources are generated only from used evidence.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, LangGraph, SQLAlchemy async, PostgreSQL pgvector, pytest, Next.js TypeScript compatibility types.

---

## Clarifications Captured Before Planning

- Do not add a new LangGraph node for planning/execution in the first version.
- `retrieved_for` means the agent or intent that caused a retrieval task to be created.
- `assigned_to` means the agents allowed to use evidence produced by a task.
- `task_id`, `evidence_id`, and warning IDs only need uniqueness within one request/graph run.
- `source_identity` must be deterministic and stable across requests.
- Use the least disruptive warning storage: `RetrievalResult.warnings: list[StructuredWarning]`. Do not add `warnings_by_id` in this first implementation.
- Add an implementation task to inspect readiness semantics and distinguish parent readiness, structured search readiness, semantic index readiness, and market aggregate readiness as far as the current code supports.
- Market retrieval must use current aggregate helpers only. If they cannot produce a grounded metric, return partial/skipped with `investment_market_data_missing`.
- Acceptance test query: `Tìm căn hộ Quận 7 dưới 5 tỷ, pháp lý ổn và có tiềm năng đầu tư không?`

## File Structure

- Modify `agent_service/contracts.py`
  - Owns Agent Service Pydantic contracts: `AgentSource`, `StructuredWarning`, `MatchedChunk`, `Evidence`, `RetrievalTask`, `RetrievalResult`, and `SpecialistResult`.
- Modify `backend/app/services/agent_service/contracts.py`
  - Mirrors service response contracts used by the backend HTTP client.
- Modify `agent_service/graph/state.py`
  - Adds registry fields: `retrieval_plan`, `retrieval_results`, `evidence_by_id`, and `evidence_for_agent`.
- Create `agent_service/graph/retrieval_planner.py`
  - Owns `build_retrieval_plan()`, `execute_retrieval_plan()`, readiness capability mapping, evidence normalization, and source mapping helpers.
- Modify `agent_service/graph/nodes.py`
  - Keeps `retrieval_planner_node` as the single graph node and wires it to the new planner/executor functions.
  - Updates `specialist_agents_node` to resolve assigned evidence IDs before calling specialists.
  - Updates `synthesizer_node` to validate `evidence_ids_used` and build final sources from registry evidence only.
- Modify `agent_service/tools/retrieval.py`
  - Allows retrieval wrappers to accept `top_k` and `rerank_to`.
- Create `agent_service/tools/market.py`
  - Normalizes current market aggregate helper output into `market_metric` evidence when enough filters exist.
- Modify `agent_service/agents/specialists.py`
  - Specialists consume normalized evidence dicts and return `SpecialistResult`-compatible dicts with status and `evidence_ids_used`.
- Modify `backend/app/services/rag/hybrid_search.py`
  - Add article filter support for `exclude_category` so news evidence can exclude legal articles.
- Modify `frontend/lib/types.ts` only if `AgentSource` response fields require TypeScript widening after backend schema changes.
- Add or modify tests:
  - `backend/tests/test_agent_retrieval_contracts.py`
  - `backend/tests/test_agent_retrieval_planner.py`
  - `backend/tests/test_agent_rag_tools.py`
  - `backend/tests/test_agent_specialists.py`
  - `backend/tests/test_agent_graph_core.py`
  - `backend/tests/test_chat_agent_service_integration.py`
  - `backend/tests/test_backend_hybrid_search.py`

---

### Task 1: Add Agent Retrieval Contracts

**Files:**
- Modify: `agent_service/contracts.py`
- Modify: `backend/app/services/agent_service/contracts.py`
- Modify: `agent_service/graph/state.py`
- Test: `backend/tests/test_agent_retrieval_contracts.py`

- [ ] **Step 1: Write failing contract tests**

Add `backend/tests/test_agent_retrieval_contracts.py`:

```python
from agent_service.contracts import (
    AgentSource,
    Evidence,
    MatchedChunk,
    RetrievalResult,
    RetrievalTask,
    SpecialistResult,
    StructuredWarning,
)


def test_agent_source_accepts_frontend_safe_fields():
    source = AgentSource(
        type="article",
        domain="legal",
        id="article:7",
        title="Luật Đất đai",
        url=None,
        snippet="Điều kiện chuyển nhượng quyền sử dụng đất.",
        location={"city": "Ho Chi Minh"},
        citation={"doc_slug": "luat-dat-dai", "dieu_number": "45"},
        score=0.91,
        metadata={"source_identity": "article:legal://luat-dat-dai"},
    )

    assert source.id == "article:7"
    assert source.domain == "legal"
    assert source.metadata["source_identity"] == "article:legal://luat-dat-dai"


def test_evidence_preserves_many_matched_chunks():
    warning = StructuredWarning(
        code="no_evidence",
        domain="property",
        message="No listing evidence was found.",
        retryable=False,
    )
    chunk_1 = MatchedChunk(
        id="chunk:1",
        chunk_type="overview",
        text="Căn hộ Quận 7 dưới 5 tỷ",
        vector_distance=0.18,
        rerank_score=0.91,
        final_score=0.91,
    )
    chunk_2 = MatchedChunk(
        id="chunk:2",
        chunk_type="description",
        text="Gần trường học và siêu thị",
        vector_distance=0.22,
        final_score=0.78,
    )

    evidence = Evidence(
        evidence_id="ev_1",
        retrieval_task_id="search_property_1",
        domain="property",
        source_type="listing",
        source_identity="listing:100",
        record={"id": 100},
        facts={"title": "Căn hộ Quận 7", "legal_status_claimed": "Sổ hồng"},
        source=AgentSource(type="listing", domain="property", id="listing:100"),
        matched_chunks=[chunk_1, chunk_2],
        retrieved_for=["property_search"],
        assigned_to=["property_search", "investment_advisor"],
        warnings=[warning],
    )

    assert len(evidence.matched_chunks) == 2
    assert evidence.assigned_to == ["property_search", "investment_advisor"]


def test_retrieval_task_result_and_specialist_result_shapes():
    task = RetrievalTask(
        task_id="search_legal_1",
        domain="legal",
        tool="search_articles",
        query="pháp lý mua căn hộ",
        filters={"category": "legal"},
        retrieved_for=["legal_advisor"],
        depends_on=[],
        dependency_mode="none",
        top_k=20,
        rerank_top_k=5,
        timeout_ms=None,
    )
    warning = StructuredWarning(
        code="source_not_ready",
        domain="legal",
        message="Legal knowledge base is not ready.",
        retryable=False,
    )
    result = RetrievalResult(
        task_id=task.task_id,
        status="skipped",
        evidence_ids=[],
        duration_ms=0,
        warnings=[warning],
        skip_reason="source_not_ready",
        error=None,
    )
    specialist = SpecialistResult(
        agent_name="legal_advisor",
        status="no_evidence",
        content="Chưa có căn cứ pháp lý để kết luận.",
        evidence_ids_used=[],
        confidence="low",
        warnings=[warning],
        missing_evidence=["legal"],
        sources=[],
    )

    assert result.status == "skipped"
    assert result.warnings[0].code == "source_not_ready"
    assert specialist.status == "no_evidence"
```

- [ ] **Step 2: Run the contract tests and verify they fail**

Run:

```powershell
pytest backend\tests\test_agent_retrieval_contracts.py -q
```

Expected: FAIL with import errors for `Evidence`, `RetrievalTask`, `RetrievalResult`, `SpecialistResult`, `StructuredWarning`, or missing fields on `AgentSource`.

- [ ] **Step 3: Implement contracts in Agent Service**

In `agent_service/contracts.py`, add imports:

```python
from typing import Any, Literal
```

Replace `AgentSource` and add the new models above `ConversationContextItem`:

```python
class StructuredWarning(BaseModel):
    code: str
    domain: str | None = None
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class MatchedChunk(BaseModel):
    id: str | None = None
    chunk_type: str | None = None
    text: str | None = None
    vector_distance: float | None = None
    semantic_score: float | None = None
    rerank_score: float | None = None
    final_score: float | None = None


class AgentSource(BaseModel):
    type: str
    domain: str | None = None
    id: str | int | None = None
    product_id: str | None = None
    title: str | None = None
    url: str | None = None
    snippet: str | None = None
    location: dict[str, Any] | str | None = None
    citation: dict[str, Any] | str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    evidence_id: str
    retrieval_task_id: str
    domain: Literal["property", "project", "news", "legal", "market"]
    source_type: Literal["listing", "project", "article", "market_metric"]
    source_identity: str
    record: dict[str, Any] = Field(default_factory=dict)
    facts: dict[str, Any] = Field(default_factory=dict)
    source: AgentSource
    matched_chunks: list[MatchedChunk] = Field(default_factory=list)
    retrieved_for: list[str] = Field(default_factory=list)
    assigned_to: list[str] = Field(default_factory=list)
    warnings: list[StructuredWarning] = Field(default_factory=list)


class RetrievalTask(BaseModel):
    task_id: str
    domain: Literal["property", "project", "news", "legal", "market"]
    tool: str
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    retrieved_for: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    dependency_mode: Literal["required", "optional_context", "none"] = "none"
    top_k: int = 20
    rerank_top_k: int | None = 5
    timeout_ms: int | None = None


class RetrievalResult(BaseModel):
    task_id: str
    status: Literal["completed", "empty", "failed", "skipped"]
    evidence_ids: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    warnings: list[StructuredWarning] = Field(default_factory=list)
    skip_reason: str | None = None
    error: dict[str, Any] | None = None


class SpecialistResult(BaseModel):
    agent_name: str
    status: Literal["completed", "partial", "no_evidence", "failed", "skipped"]
    content: str
    evidence_ids_used: list[str] = Field(default_factory=list)
    confidence: float | str | None = None
    warnings: list[StructuredWarning] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    sources: list[AgentSource] = Field(default_factory=list)
```

Update `TraceSummary` warnings to accept structured warnings while preserving strings:

```python
class TraceSummary(BaseModel):
    intent: str = "unknown"
    agents: list[str] = Field(default_factory=list)
    source_count: int = 0
    latency_ms: float = 0.0
    warnings: list[str | StructuredWarning] = Field(default_factory=list)
```

- [ ] **Step 4: Mirror contracts in backend client module**

Apply the same model definitions and `TraceSummary` warning type change in `backend/app/services/agent_service/contracts.py`.

- [ ] **Step 5: Extend graph state**

In `agent_service/graph/state.py`, import the new contracts:

```python
from agent_service.contracts import (
    AgentChatRequest,
    AgentSource,
    Evidence,
    MemoryProposal,
    RetrievalResult,
    RetrievalTask,
    StructuredWarning,
)
```

Add fields to `AgentGraphState`:

```python
    retrieval_plan: list[RetrievalTask]
    retrieval_results: dict[str, RetrievalResult]
    evidence_by_id: dict[str, Evidence]
    evidence_for_agent: dict[str, list[str]]
    warnings: list[str | StructuredWarning]
```

Keep the existing `evidence: dict[str, list[dict[str, Any]]]` field for compatibility during the migration.

- [ ] **Step 6: Run contract tests and existing agent tests**

Run:

```powershell
pytest backend\tests\test_agent_retrieval_contracts.py backend\tests\test_agent_graph_core.py -q
```

Expected: PASS for the new contract tests. Existing graph tests may fail later if they assert string-only warnings; if so, adjust assertions to accept structured warnings in Task 8.

- [ ] **Step 7: Commit contracts**

Run:

```powershell
git add agent_service\contracts.py backend\app\services\agent_service\contracts.py agent_service\graph\state.py backend\tests\test_agent_retrieval_contracts.py
git commit -m "feat: add agent retrieval evidence contracts"
```

---

### Task 2: Support Article Exclusion Filters In Hybrid Search

**Files:**
- Modify: `backend/app/services/rag/hybrid_search.py`
- Test: `backend/tests/test_backend_hybrid_search.py`

- [ ] **Step 1: Add failing filter tests**

Append to `backend/tests/test_backend_hybrid_search.py`:

```python
from app.services.rag.hybrid_search import build_article_filter_clauses


def test_article_filter_supports_excluding_legal_category():
    clauses, params = build_article_filter_clauses({"exclude_category": "legal"})

    assert "category != :exclude_category" in clauses
    assert params == {"exclude_category": "legal"}


def test_article_filter_keeps_exact_category_for_legal_retrieval():
    clauses, params = build_article_filter_clauses({"category": "legal"})

    assert "category = :category" in clauses
    assert params == {"category": "legal"}
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```powershell
pytest backend\tests\test_backend_hybrid_search.py::test_article_filter_supports_excluding_legal_category backend\tests\test_backend_hybrid_search.py::test_article_filter_keeps_exact_category_for_legal_retrieval -q
```

Expected: first test FAILS because `exclude_category` is not handled.

- [ ] **Step 3: Implement article exclusion filter**

In `backend/app/services/rag/hybrid_search.py`, update `build_article_filter_clauses()`:

```python
def build_article_filter_clauses(filters: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if filters.get("category"):
        clauses.append("category = :category")
        params["category"] = filters["category"]
    if filters.get("exclude_category"):
        clauses.append("category != :exclude_category")
        params["exclude_category"] = filters["exclude_category"]
    return clauses or ["1=1"], params
```

- [ ] **Step 4: Run hybrid search tests**

Run:

```powershell
pytest backend\tests\test_backend_hybrid_search.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit article filter support**

Run:

```powershell
git add backend\app\services\rag\hybrid_search.py backend\tests\test_backend_hybrid_search.py
git commit -m "feat: support article category exclusion filters"
```

---

### Task 3: Build Planner Contracts, Readiness Capabilities, And Plans

**Files:**
- Create: `agent_service/graph/retrieval_planner.py`
- Test: `backend/tests/test_agent_retrieval_planner.py`

- [ ] **Step 1: Write failing planner tests**

Create `backend/tests/test_agent_retrieval_planner.py`:

```python
from agent_service.contracts import AgentChatRequest
from agent_service.graph.retrieval_planner import (
    build_retrieval_plan,
    readiness_capabilities,
)


def _state(message, agents, readiness=None):
    return {
        "request": AgentChatRequest(
            request_id="req-plan",
            session_id="session-1",
            message=message,
        ),
        "agents_to_run": agents,
        "readiness": readiness or {
            "listings": {"status": "ready", "parent_count": 10, "chunk_count": 30},
            "legal": {"status": "ready", "parent_count": 2, "chunk_count": 9},
            "projects": {"status": "ready", "parent_count": 3, "chunk_count": 8},
            "news": {"status": "ready", "parent_count": 4, "chunk_count": 12},
        },
    }


def test_readiness_capabilities_distinguish_parent_and_semantic_index():
    caps = readiness_capabilities({
        "listings": {"status": "not_ready", "parent_count": 5, "chunk_count": 0},
    })

    assert caps["property"]["parent_ready"] is True
    assert caps["property"]["structured_search_ready"] is True
    assert caps["property"]["semantic_index_ready"] is False
    assert caps["property"]["market_aggregate_ready"] is True


def test_build_retrieval_plan_for_mixed_query_creates_property_and_legal_tasks():
    plan = build_retrieval_plan(_state(
        "Tìm căn hộ Quận 7 dưới 5 tỷ, pháp lý ổn và có tiềm năng đầu tư không?",
        ["legal_advisor", "investment_advisor", "property_search"],
    ))

    tasks = {task.task_id: task for task in plan}
    assert "search_property_1" in tasks
    assert "search_legal_1" in tasks
    assert tasks["search_property_1"].tool == "search_listings"
    assert tasks["search_property_1"].filters["district"] == "Quan 7"
    assert tasks["search_property_1"].filters["max_price"] == 5.0
    assert tasks["search_property_1"].filters["property_type"] == "Can ho"
    assert tasks["search_property_1"].retrieved_for == ["property_search"]
    assert tasks["search_property_1"].dependency_mode == "none"
    assert tasks["search_legal_1"].filters == {"category": "legal"}


def test_investment_reuses_property_task_without_duplicate_listing_task():
    plan = build_retrieval_plan(_state(
        "Tìm căn hộ Quận 7 dưới 5 tỷ để đầu tư",
        ["investment_advisor", "property_search"],
    ))

    listing_tasks = [task for task in plan if task.tool == "search_listings"]
    assert len(listing_tasks) == 1
    assert listing_tasks[0].retrieved_for == ["property_search"]


def test_planner_does_not_add_project_or_news_for_plain_investment_query():
    plan = build_retrieval_plan(_state(
        "Tìm căn hộ Quận 7 dưới 5 tỷ để đầu tư",
        ["investment_advisor", "property_search"],
    ))

    assert all(task.domain not in {"project", "news"} for task in plan)


def test_planner_adds_news_when_investment_query_mentions_market_movement():
    plan = build_retrieval_plan(_state(
        "Đầu tư căn hộ Quận 7, có tin tức biến động thị trường gần đây không?",
        ["investment_advisor", "news_agent", "property_search"],
    ))

    news_tasks = [task for task in plan if task.domain == "news"]
    assert len(news_tasks) == 1
    assert news_tasks[0].filters == {"exclude_category": "legal"}
```

- [ ] **Step 2: Run planner tests and verify failure**

Run:

```powershell
pytest backend\tests\test_agent_retrieval_planner.py -q
```

Expected: FAIL because `agent_service.graph.retrieval_planner` does not exist.

- [ ] **Step 3: Implement planner module skeleton and filter extraction**

Create `agent_service/graph/retrieval_planner.py`:

```python
from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

from agent_service.contracts import (
    AgentSource,
    Evidence,
    MatchedChunk,
    RetrievalResult,
    RetrievalTask,
    StructuredWarning,
)
from agent_service.graph.state import AgentGraphState
from agent_service.tools.retrieval import (
    RetrievalTrace,
    _run_hybrid_tool,
)


DOMAIN_SOURCE = {
    "property": "listings",
    "project": "projects",
    "news": "news",
    "legal": "legal",
    "market": "listings",
}


def _strip_accents(value: str | None) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").lower()


def _extract_filters(query: str) -> dict[str, Any]:
    normalized = _strip_accents(query)
    filters: dict[str, Any] = {}
    if any(term in normalized for term in ("thue", "cho thue")):
        filters["listing_type"] = "rent"
    elif any(term in normalized for term in ("tim", "mua", "ban", "dau tu")):
        filters["listing_type"] = "sale"
    if "can ho" in normalized or "chung cu" in normalized:
        filters["property_type"] = "Can ho"
    district_match = re.search(r"\b(?:quan|q)\s*(\d{1,2})\b", normalized)
    if district_match:
        filters["district"] = f"Quan {district_match.group(1)}"
    max_price_match = re.search(
        r"(?:duoi|toi da|khong qua)\s*(\d+(?:[\.,]\d+)?)\s*(?:ty|ti)",
        normalized,
    )
    if max_price_match:
        filters["max_price"] = float(max_price_match.group(1).replace(",", "."))
    return filters


def readiness_capabilities(readiness: dict[str, Any]) -> dict[str, dict[str, bool]]:
    capabilities: dict[str, dict[str, bool]] = {}
    for domain, source_name in DOMAIN_SOURCE.items():
        source = readiness.get(source_name, {})
        parent_count = int(source.get("parent_count") or 0) if isinstance(source, dict) else 0
        chunk_count = int(source.get("chunk_count") or 0) if isinstance(source, dict) else 0
        capabilities[domain] = {
            "parent_ready": parent_count > 0,
            "structured_search_ready": parent_count > 0,
            "semantic_index_ready": parent_count > 0 and chunk_count > 0,
            "market_aggregate_ready": domain == "market" and parent_count > 0,
        }
    return capabilities


def _needs_project(query: str) -> bool:
    normalized = _strip_accents(query)
    return any(term in normalized for term in ("du an", "chu dau tu", "ha tang"))


def _needs_news(query: str) -> bool:
    normalized = _strip_accents(query)
    return any(term in normalized for term in ("tin tuc", "bien dong", "cap nhat", "thi truong gan day"))
```

- [ ] **Step 4: Implement build_retrieval_plan**

Append this function to `agent_service/graph/retrieval_planner.py`:

```python
def build_retrieval_plan(state: AgentGraphState) -> list[RetrievalTask]:
    request = state["request"]
    agents = list(state.get("agents_to_run", []))
    readiness = state.get("readiness", {})
    caps = readiness_capabilities(readiness)
    query = request.message
    listing_filters = _extract_filters(query)
    plan: list[RetrievalTask] = []

    if "property_search" in agents and caps["property"]["semantic_index_ready"]:
        plan.append(
            RetrievalTask(
                task_id="search_property_1",
                domain="property",
                tool="search_listings",
                query=query,
                filters=listing_filters,
                retrieved_for=["property_search"],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    if "legal_advisor" in agents and caps["legal"]["semantic_index_ready"]:
        plan.append(
            RetrievalTask(
                task_id="search_legal_1",
                domain="legal",
                tool="search_articles",
                query=query,
                filters={"category": "legal"},
                retrieved_for=["legal_advisor"],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    if "project_agent" in agents and caps["project"]["semantic_index_ready"]:
        plan.append(
            RetrievalTask(
                task_id="search_project_1",
                domain="project",
                tool="search_projects",
                query=query,
                filters={key: value for key, value in listing_filters.items() if key in {"district", "city"}},
                retrieved_for=["project_agent"],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    should_search_news = "news_agent" in agents or (
        "investment_advisor" in agents and _needs_news(query)
    )
    if should_search_news and caps["news"]["semantic_index_ready"]:
        plan.append(
            RetrievalTask(
                task_id="search_news_1",
                domain="news",
                tool="search_articles",
                query=query,
                filters={"exclude_category": "legal"},
                retrieved_for=["news_agent" if "news_agent" in agents else "investment_advisor"],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    should_search_project_for_investment = (
        "investment_advisor" in agents
        and "project_agent" not in agents
        and _needs_project(query)
        and caps["project"]["semantic_index_ready"]
    )
    if should_search_project_for_investment:
        plan.append(
            RetrievalTask(
                task_id="search_project_for_investment_1",
                domain="project",
                tool="search_projects",
                query=query,
                filters={key: value for key, value in listing_filters.items() if key in {"district", "city"}},
                retrieved_for=["investment_advisor"],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    return plan
```

- [ ] **Step 5: Run planner tests**

Run:

```powershell
pytest backend\tests\test_agent_retrieval_planner.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit planner plan-building**

Run:

```powershell
git add agent_service\graph\retrieval_planner.py backend\tests\test_agent_retrieval_planner.py
git commit -m "feat: build agent retrieval plans"
```

---

### Task 4: Normalize Evidence And Execute Retrieval Plans

**Files:**
- Modify: `agent_service/graph/retrieval_planner.py`
- Modify: `agent_service/tools/retrieval.py`
- Create: `agent_service/tools/market.py`
- Test: `backend/tests/test_agent_retrieval_planner.py`
- Test: `backend/tests/test_agent_rag_tools.py`

- [ ] **Step 1: Extend retrieval wrapper tests for limits**

In `backend/tests/test_agent_rag_tools.py`, update or add:

```python
@pytest.mark.asyncio
async def test_search_listings_accepts_task_limits(monkeypatch):
    called = {}

    async def fake_run_hybrid_tool(**kwargs):
        called["top_k"] = kwargs["top_k"]
        called["rerank_to"] = kwargs["rerank_to"]
        return []

    monkeypatch.setattr("agent_service.tools.retrieval._run_hybrid_tool", fake_run_hybrid_tool)
    trace = RetrievalTrace(request_id="req-limits")

    await search_listings("Tim nha", {"district": "Quan 7"}, trace, top_k=9, rerank_to=4)

    assert called == {"top_k": 9, "rerank_to": 4}
```

- [ ] **Step 2: Run wrapper test and verify failure**

Run:

```powershell
pytest backend\tests\test_agent_rag_tools.py::test_search_listings_accepts_task_limits -q
```

Expected: FAIL because `search_listings()` does not accept `top_k` or `rerank_to`.

- [ ] **Step 3: Update retrieval wrappers**

In `agent_service/tools/retrieval.py`, update the three public tool functions:

```python
async def search_listings(
    query: str,
    filters: dict[str, Any] | None,
    trace: RetrievalTrace,
    *,
    top_k: int = 20,
    rerank_to: int = 5,
) -> list[dict[str, Any]]:
    return await _run_hybrid_tool(
        query=query,
        filters=filters,
        trace=trace,
        tool_name="search_listings",
        parent_type="listing",
        top_k=top_k,
        rerank_to=rerank_to,
    )


async def search_projects(
    query: str,
    filters: dict[str, Any] | None,
    trace: RetrievalTrace,
    *,
    top_k: int = 20,
    rerank_to: int = 5,
) -> list[dict[str, Any]]:
    return await _run_hybrid_tool(
        query=query,
        filters=filters,
        trace=trace,
        tool_name="search_projects",
        parent_type="project",
        top_k=top_k,
        rerank_to=rerank_to,
    )


async def search_articles(
    query: str,
    filters: dict[str, Any] | None,
    trace: RetrievalTrace,
    *,
    top_k: int = 20,
    rerank_to: int = 5,
) -> list[dict[str, Any]]:
    return await _run_hybrid_tool(
        query=query,
        filters=filters,
        trace=trace,
        tool_name="search_articles",
        parent_type="article",
        top_k=top_k,
        rerank_to=rerank_to,
    )
```

- [ ] **Step 4: Add executor and normalization tests**

Append to `backend/tests/test_agent_retrieval_planner.py`:

```python
import pytest

from agent_service.contracts import RetrievalTask
from agent_service.graph import retrieval_planner
from agent_service.graph.retrieval_planner import execute_retrieval_plan


@pytest.mark.asyncio
async def test_execute_plan_normalizes_listing_and_assigns_to_investment(monkeypatch):
    async def fake_run_tool(**kwargs):
        assert kwargs["parent_type"] == "listing"
        return [
            {
                "id": 100,
                "product_id": "p-100",
                "title": "Căn hộ Quận 7",
                "price": 4.8,
                "price_text": "4.8 tỷ",
                "area": 75,
                "area_text": "75 m2",
                "price_per_m2": 64,
                "district": "Quan 7",
                "city": "Ho Chi Minh",
                "legal_status": "Sổ hồng",
                "url": "https://example.test/p-100",
                "matched_chunk": {
                    "id": 501,
                    "chunk_type": "overview",
                    "text": "Căn hộ Quận 7 giá 4.8 tỷ",
                    "distance": 0.18,
                    "rerank_score": 0.91,
                },
            }
        ]

    monkeypatch.setattr(retrieval_planner, "_run_hybrid_tool", fake_run_tool)
    state = _state(
        "Tìm căn hộ Quận 7 dưới 5 tỷ để đầu tư",
        ["property_search", "investment_advisor"],
    )
    plan = [
        RetrievalTask(
            task_id="search_property_1",
            domain="property",
            tool="search_listings",
            query=state["request"].message,
            filters={"district": "Quan 7"},
            retrieved_for=["property_search"],
            top_k=20,
            rerank_top_k=5,
        )
    ]

    update = await execute_retrieval_plan(plan, state)

    evidence_ids = update["evidence_for_agent"]["property_search"]
    assert evidence_ids == update["evidence_for_agent"]["investment_advisor"]
    evidence = update["evidence_by_id"][evidence_ids[0]]
    assert evidence.source_identity == "listing:p-100"
    assert evidence.facts["legal_status_claimed"] == "Sổ hồng"
    assert evidence.matched_chunks[0].vector_distance == 0.18
    assert evidence.matched_chunks[0].final_score == 0.91
    assert update["retrieval_results"]["search_property_1"].status == "completed"


@pytest.mark.asyncio
async def test_execute_plan_empty_result_has_empty_status(monkeypatch):
    async def fake_run_tool(**kwargs):
        return []

    monkeypatch.setattr(retrieval_planner, "_run_hybrid_tool", fake_run_tool)
    state = _state("Tìm căn hộ Quận 7", ["property_search"])
    plan = [
        RetrievalTask(
            task_id="search_property_1",
            domain="property",
            tool="search_listings",
            query=state["request"].message,
            filters={},
            retrieved_for=["property_search"],
        )
    ]

    update = await execute_retrieval_plan(plan, state)

    assert update["retrieval_results"]["search_property_1"].status == "empty"
    assert update["evidence_by_id"] == {}


@pytest.mark.asyncio
async def test_execute_plan_failure_is_isolated(monkeypatch):
    async def fake_run_tool(**kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(retrieval_planner, "_run_hybrid_tool", fake_run_tool)
    state = _state("Pháp lý mua căn hộ", ["legal_advisor"])
    plan = [
        RetrievalTask(
            task_id="search_legal_1",
            domain="legal",
            tool="search_articles",
            query=state["request"].message,
            filters={"category": "legal"},
            retrieved_for=["legal_advisor"],
        )
    ]

    update = await execute_retrieval_plan(plan, state)

    result = update["retrieval_results"]["search_legal_1"]
    assert result.status == "failed"
    assert result.warnings[0].code == "retrieval_error"
```

- [ ] **Step 5: Implement evidence normalization helpers**

Append these helpers to `agent_service/graph/retrieval_planner.py`:

```python
def structured_warning(
    *,
    code: str,
    domain: str | None,
    message: str,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> StructuredWarning:
    return StructuredWarning(
        code=code,
        domain=domain,
        message=message,
        retryable=retryable,
        details=details or {},
    )


def _stable_source_identity(domain: str, source_type: str, record: dict[str, Any]) -> str:
    if source_type == "listing":
        key = record.get("product_id") or record.get("id")
    elif source_type == "project":
        key = record.get("slug") or record.get("url") or record.get("id")
    elif source_type == "article":
        key = record.get("url") or record.get("id")
    else:
        key = record.get("source_identity") or record.get("id") or domain
    return f"{source_type}:{key}"


def _location_fact(record: dict[str, Any]) -> dict[str, Any] | None:
    location = {
        "ward": record.get("ward"),
        "district": record.get("district"),
        "city": record.get("city"),
        "address": record.get("address") or record.get("location"),
    }
    clean = {key: value for key, value in location.items() if value}
    return clean or None


def _score_from_chunk(raw_chunk: dict[str, Any]) -> tuple[float | None, float | None]:
    rerank_score = raw_chunk.get("rerank_score")
    if rerank_score is not None:
        return float(rerank_score), float(rerank_score)
    distance = raw_chunk.get("distance")
    if distance is None:
        return None, None
    return None, None


def _matched_chunks_from_record(record: dict[str, Any]) -> list[MatchedChunk]:
    raw_chunks = record.get("matched_chunks")
    if not raw_chunks and record.get("matched_chunk"):
        raw_chunks = [record["matched_chunk"]]
    chunks: list[MatchedChunk] = []
    for index, raw_chunk in enumerate(raw_chunks or []):
        if not isinstance(raw_chunk, dict):
            continue
        rerank_score, final_score = _score_from_chunk(raw_chunk)
        chunks.append(
            MatchedChunk(
                id=str(raw_chunk.get("id") or f"chunk:{index}"),
                chunk_type=raw_chunk.get("chunk_type"),
                text=raw_chunk.get("text"),
                vector_distance=(
                    float(raw_chunk["distance"])
                    if raw_chunk.get("distance") is not None
                    else None
                ),
                semantic_score=None,
                rerank_score=rerank_score,
                final_score=final_score,
            )
        )
    return chunks


def _source_from_normalized(
    *,
    domain: str,
    source_type: str,
    source_identity: str,
    record: dict[str, Any],
    chunks: list[MatchedChunk],
) -> AgentSource:
    title = record.get("title") or record.get("name")
    snippet = next((chunk.text for chunk in chunks if chunk.text), None)
    score = next((chunk.final_score for chunk in chunks if chunk.final_score is not None), None)
    return AgentSource(
        type=source_type,
        domain=domain,
        id=source_identity,
        product_id=record.get("product_id"),
        title=title,
        url=record.get("url"),
        snippet=snippet,
        location=_location_fact(record),
        citation=record.get("citation"),
        score=score,
        metadata={
            key: value
            for key, value in {
                "source_identity": source_identity,
                "price_text": record.get("price_text") or record.get("price_range"),
                "area_text": record.get("area_text") or record.get("area_range"),
                "category": record.get("category"),
            }.items()
            if value is not None
        },
    )


def _facts_from_record(domain: str, source_type: str, record: dict[str, Any]) -> dict[str, Any]:
    facts = {
        "title": record.get("title") or record.get("name"),
        "price": record.get("price"),
        "price_text": record.get("price_text") or record.get("price_range"),
        "area": record.get("area"),
        "area_text": record.get("area_text") or record.get("area_range"),
        "price_per_m2": record.get("price_per_m2"),
        "location": _location_fact(record),
        "category": record.get("category"),
        "legal_status_claimed": record.get("legal_status"),
    }
    return {key: value for key, value in facts.items() if value is not None}


def normalize_record_to_evidence(
    *,
    record: dict[str, Any],
    task: RetrievalTask,
    evidence_index: int,
    assigned_to: list[str],
) -> Evidence:
    source_type = {
        "property": "listing",
        "project": "project",
        "news": "article",
        "legal": "article",
        "market": "market_metric",
    }[task.domain]
    source_identity = _stable_source_identity(task.domain, source_type, record)
    chunks = _matched_chunks_from_record(record)
    source = _source_from_normalized(
        domain=task.domain,
        source_type=source_type,
        source_identity=source_identity,
        record=record,
        chunks=chunks,
    )
    return Evidence(
        evidence_id=f"ev_{task.task_id}_{evidence_index}",
        retrieval_task_id=task.task_id,
        domain=task.domain,
        source_type=source_type,
        source_identity=source_identity,
        record=record,
        facts=_facts_from_record(task.domain, source_type, record),
        source=source,
        matched_chunks=chunks,
        retrieved_for=task.retrieved_for,
        assigned_to=assigned_to,
        warnings=[],
    )
```

- [ ] **Step 6: Implement assignment and executor**

Append to `agent_service/graph/retrieval_planner.py`:

```python
def _assigned_agents_for_task(task: RetrievalTask, agents_to_run: list[str]) -> list[str]:
    assigned = list(task.retrieved_for)
    if task.domain == "property" and "investment_advisor" in agents_to_run:
        assigned.append("investment_advisor")
    if task.domain in {"project", "news", "market"} and "investment_advisor" in agents_to_run:
        assigned.append("investment_advisor")
    return list(dict.fromkeys(assigned))


def _parent_type_for_task(task: RetrievalTask) -> str:
    return {
        "property": "listing",
        "project": "project",
        "news": "article",
        "legal": "article",
    }[task.domain]


async def execute_retrieval_plan(
    plan: list[RetrievalTask],
    state: AgentGraphState,
) -> dict[str, Any]:
    started_all = time.perf_counter()
    request = state["request"]
    agents_to_run = list(state.get("agents_to_run", []))
    evidence_by_id: dict[str, Evidence] = {}
    evidence_for_agent: dict[str, list[str]] = {agent: [] for agent in agents_to_run}
    retrieval_results: dict[str, RetrievalResult] = {}
    warnings: list[StructuredWarning] = []
    trace_events: list[dict[str, Any]] = [
        {
            "event": "retrieval_plan_created",
            "task_count": len(plan),
            "task_ids": [task.task_id for task in plan],
        }
    ]

    for task in plan:
        task_started = time.perf_counter()
        trace_events.append({"event": "retrieval_task_started", "task_id": task.task_id})
        try:
            if task.domain == "market":
                records: list[dict[str, Any]] = []
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
            retrieval_results[task.task_id] = RetrievalResult(
                task_id=task.task_id,
                status="failed",
                evidence_ids=[],
                duration_ms=round((time.perf_counter() - task_started) * 1000),
                warnings=[warning],
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )
            trace_events.append({"event": "retrieval_task_failed", "task_id": task.task_id})
            continue

        if not records:
            warning = structured_warning(
                code="no_evidence",
                domain=task.domain,
                message=f"No evidence found for {task.domain}.",
                retryable=False,
                details={"task_id": task.task_id},
            )
            warnings.append(warning)
            retrieval_results[task.task_id] = RetrievalResult(
                task_id=task.task_id,
                status="empty",
                evidence_ids=[],
                duration_ms=round((time.perf_counter() - task_started) * 1000),
                warnings=[warning],
            )
            trace_events.append({"event": "retrieval_task_empty", "task_id": task.task_id})
            continue

        assigned_to = _assigned_agents_for_task(task, agents_to_run)
        evidence_ids: list[str] = []
        for index, record in enumerate(records, start=1):
            evidence = normalize_record_to_evidence(
                record=record,
                task=task,
                evidence_index=index,
                assigned_to=assigned_to,
            )
            evidence_by_id[evidence.evidence_id] = evidence
            evidence_ids.append(evidence.evidence_id)
            for agent in assigned_to:
                evidence_for_agent.setdefault(agent, []).append(evidence.evidence_id)

        retrieval_results[task.task_id] = RetrievalResult(
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

    return {
        "retrieval_plan": plan,
        "retrieval_results": retrieval_results,
        "evidence_by_id": evidence_by_id,
        "evidence_for_agent": evidence_for_agent,
        "retrieval_events": trace_events,
        "warnings": [*state.get("warnings", []), *warnings],
        "retrieval_duration_ms": round((time.perf_counter() - started_all) * 1000),
    }
```

- [ ] **Step 7: Create market tool with current helper only**

Create `agent_service/tools/market.py`:

```python
from __future__ import annotations

from typing import Any

from chatbot.tools.market_stats import district_price_overview


async def lookup_market_metrics(filters: dict[str, Any]) -> list[dict[str, Any]]:
    city = filters.get("city")
    listing_type = filters.get("listing_type") or "sale"
    property_type = filters.get("property_type")
    if not city:
        return []
    rows = await district_price_overview(
        city=str(city),
        listing_type=str(listing_type),
        property_type=str(property_type) if property_type else None,
    )
    return [
        {
            "source_identity": (
                f"market:{row.get('district')}:{property_type or 'all'}:"
                f"avg_price_per_m2:current"
            ),
            "metric": "avg_price_per_m2",
            "value": row.get("avg_price_per_m2"),
            "unit": "million VND/m2",
            "location": {"city": city, "district": row.get("district")},
            "property_type": property_type,
            "period": "current_snapshot",
            "record": row,
        }
        for row in rows
        if row.get("avg_price_per_m2") is not None
    ]
```

This tool is not yet wired in Task 4. Task 7 wires market evidence into investment behavior with skip/partial warnings.

- [ ] **Step 8: Run executor and tool tests**

Run:

```powershell
pytest backend\tests\test_agent_retrieval_planner.py backend\tests\test_agent_rag_tools.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit executor and normalization**

Run:

```powershell
git add agent_service\graph\retrieval_planner.py agent_service\tools\retrieval.py agent_service\tools\market.py backend\tests\test_agent_retrieval_planner.py backend\tests\test_agent_rag_tools.py
git commit -m "feat: execute retrieval plans into evidence registry"
```

---

### Task 5: Wire Planner Node Without Adding Graph Nodes

**Files:**
- Modify: `agent_service/graph/nodes.py`
- Test: `backend/tests/test_agent_graph_core.py`

- [ ] **Step 1: Add graph test for planner/executor function usage**

Append to `backend/tests/test_agent_graph_core.py`:

```python
@pytest.mark.asyncio
async def test_retrieval_planner_node_uses_single_node_with_testable_functions(monkeypatch):
    request = AgentChatRequest(
        request_id="req-planner-node",
        message="Tim can ho Quan 7",
        session_id="session-1",
    )
    state = {
        "request": request,
        "agents_to_run": ["property_search"],
        "readiness": {
            "listings": {"status": "ready", "parent_count": 1, "chunk_count": 1},
        },
        "trace_steps": [],
        "warnings": [],
    }
    called = {}

    def fake_build(input_state):
        called["build"] = input_state["request"].request_id
        return []

    async def fake_execute(plan, input_state):
        called["execute"] = len(plan)
        return {
            "retrieval_plan": [],
            "retrieval_results": {},
            "evidence_by_id": {},
            "evidence_for_agent": {"property_search": []},
            "retrieval_events": [],
            "warnings": [],
        }

    monkeypatch.setattr(nodes, "build_retrieval_plan", fake_build)
    monkeypatch.setattr(nodes, "execute_retrieval_plan", fake_execute)

    result = await nodes.retrieval_planner_node(state)

    assert called == {"build": "req-planner-node", "execute": 0}
    assert result["evidence_for_agent"] == {"property_search": []}
    assert result["trace_steps"][-1]["step_name"] == "retrieval_planner"
```

- [ ] **Step 2: Run the focused graph test and verify failure**

Run:

```powershell
pytest backend\tests\test_agent_graph_core.py::test_retrieval_planner_node_uses_single_node_with_testable_functions -q
```

Expected: FAIL because `retrieval_planner_node` is sync and does not call the planner functions.

- [ ] **Step 3: Import planner functions and make retrieval planner node async**

In `agent_service/graph/nodes.py`, add:

```python
from agent_service.graph.retrieval_planner import (
    build_retrieval_plan,
    execute_retrieval_plan,
)
```

Replace `retrieval_planner_node` with:

```python
async def retrieval_planner_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    plan = build_retrieval_plan(state)
    update = await execute_retrieval_plan(plan, state)
    return {
        **update,
        "trace_steps": _append_trace(
            {**state, **update},
            "retrieval_planner",
            start_time,
            {
                "planned_tasks": [task.task_id for task in plan],
                "evidence_count": len(update.get("evidence_by_id", {})),
                "retrieval_events": update.get("retrieval_events", []),
            },
        ),
    }
```

LangGraph accepts async node callables in the existing async graph.

- [ ] **Step 4: Run graph tests**

Run:

```powershell
pytest backend\tests\test_agent_graph_core.py -q
```

Expected: PASS or failures only from specialist/synthesizer expectations that later tasks update.

- [ ] **Step 5: Commit graph planner wiring**

Run:

```powershell
git add agent_service\graph\nodes.py backend\tests\test_agent_graph_core.py
git commit -m "feat: wire retrieval planner node to planner executor"
```

---

### Task 6: Update Specialists To Use Assigned Evidence IDs

**Files:**
- Modify: `agent_service/graph/nodes.py`
- Modify: `agent_service/agents/specialists.py`
- Test: `backend/tests/test_agent_specialists.py`

- [ ] **Step 1: Add anti-hallucination specialist tests**

Append to `backend/tests/test_agent_specialists.py`:

```python
from agent_service.contracts import AgentSource, Evidence, MatchedChunk


def _listing_evidence(evidence_id="ev_listing_1"):
    return Evidence(
        evidence_id=evidence_id,
        retrieval_task_id="search_property_1",
        domain="property",
        source_type="listing",
        source_identity="listing:p-1",
        record={},
        facts={
            "title": "Căn hộ Quận 7",
            "price_text": "4.8 tỷ",
            "area_text": "75 m2",
            "location": {"district": "Quan 7", "city": "Ho Chi Minh"},
            "legal_status_claimed": "Sổ hồng",
        },
        source=AgentSource(type="listing", domain="property", id="listing:p-1"),
        matched_chunks=[MatchedChunk(text="Căn hộ Quận 7 giá 4.8 tỷ", final_score=0.91)],
        retrieved_for=["property_search"],
        assigned_to=["property_search", "investment_advisor"],
    ).model_dump(mode="python")


@pytest.mark.asyncio
async def test_property_agent_reports_no_evidence_without_fake_listing():
    result = await run_property_agent(
        query="Tim can ho Quan 7",
        evidence=[],
        preferences={},
        readiness={"listings": {"status": "ready"}},
    )

    assert result["status"] == "no_evidence"
    assert result["evidence_ids_used"] == []
    assert "Can ho Quan 7 - 4.8 ty" not in result["content"]


@pytest.mark.asyncio
async def test_property_agent_uses_evidence_ids_from_assigned_evidence():
    result = await run_property_agent(
        query="Tim can ho Quan 7",
        evidence=[_listing_evidence()],
        preferences={},
        readiness={"listings": {"status": "ready"}},
    )

    assert result["status"] == "completed"
    assert result["evidence_ids_used"] == ["ev_listing_1"]
    assert "Căn hộ Quận 7" in result["content"]


@pytest.mark.asyncio
async def test_legal_agent_does_not_use_listing_legal_claim_as_legal_proof():
    result = await run_legal_agent(
        query="pháp lý ổn không",
        evidence=[_listing_evidence()],
        preferences={},
        readiness={"legal": {"status": "ready"}},
    )

    assert result["status"] == "no_evidence"
    assert result["evidence_ids_used"] == []
    assert "đủ điều kiện pháp lý" not in result["content"].lower()


@pytest.mark.asyncio
async def test_investment_agent_warns_when_market_metric_missing():
    result = await run_investment_agent(
        query="đầu tư căn hộ này",
        evidence=[_listing_evidence()],
        preferences={},
        readiness={"listings": {"status": "ready"}},
    )

    assert result["status"] == "partial"
    assert result["evidence_ids_used"] == ["ev_listing_1"]
    assert any(
        getattr(warning, "code", None) == "investment_market_data_missing"
        or warning.get("code") == "investment_market_data_missing"
        for warning in result["warnings"]
    )
    assert "ROI" not in result["content"]
```

- [ ] **Step 2: Run specialist tests and verify failure**

Run:

```powershell
pytest backend\tests\test_agent_specialists.py -q
```

Expected: FAIL because specialists do not return `status` or `evidence_ids_used`.

- [ ] **Step 3: Update specialist result helper**

In `agent_service/agents/specialists.py`, import:

```python
from agent_service.contracts import StructuredWarning
```

Replace `_agent_result` with:

```python
def _agent_result(
    *,
    agent_name: str,
    content: str,
    status: str,
    evidence_ids_used: list[str] | None = None,
    sources: list[dict[str, Any]] | None = None,
    confidence: float | str | None = None,
    warnings: list[Any] | None = None,
    missing_evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "agent_name": agent_name,
        "status": status,
        "content": content,
        "evidence_ids_used": evidence_ids_used or [],
        "sources": sources or [],
        "confidence": confidence,
        "warnings": warnings or [],
        "missing_evidence": missing_evidence or [],
    }
```

Add helper functions:

```python
def _warning(code: str, domain: str, message: str, *, retryable: bool = False) -> StructuredWarning:
    return StructuredWarning(
        code=code,
        domain=domain,
        message=message,
        retryable=retryable,
        details={},
    )


def _evidence_domain(record: dict[str, Any]) -> str | None:
    return record.get("domain")


def _evidence_facts(record: dict[str, Any]) -> dict[str, Any]:
    facts = record.get("facts") or {}
    return facts if isinstance(facts, dict) else {}


def _evidence_id(record: dict[str, Any]) -> str | None:
    value = record.get("evidence_id")
    return str(value) if value else None


def _describe_evidence(record: dict[str, Any]) -> str:
    facts = _evidence_facts(record)
    title = facts.get("title") or "Nguon khong co tieu de"
    location = facts.get("location")
    if isinstance(location, dict):
        location_text = ", ".join(
            str(value)
            for value in (location.get("district"), location.get("city"))
            if value
        )
    else:
        location_text = str(location) if location else ""
    details = [
        str(title),
        location_text,
        str(facts.get("price_text") or ""),
        str(facts.get("area_text") or ""),
    ]
    return " - ".join(part for part in details if part)
```

- [ ] **Step 4: Update property/project/news/legal agents**

Update each agent to filter by domain and return used IDs. For `run_property_agent`, use:

```python
property_evidence = [item for item in evidence if _evidence_domain(item) == "property"]
if not property_evidence:
    return _agent_result(
        agent_name="property_search",
        status="no_evidence",
        content=(
            "Chua co bang chung listing phu hop de khang dinh bat dong san cu the. "
            "Toi chi co the goi y bo sung tieu chi tim kiem truoc khi so sanh."
        ),
        confidence="low",
        warnings=[_warning("no_evidence", "property", "No listing evidence was found.")],
        missing_evidence=["property"],
    )

used_ids = [value for item in property_evidence if (value := _evidence_id(item))]
lines = [_describe_evidence(item) for item in property_evidence]
return _agent_result(
    agent_name="property_search",
    status="completed",
    content=(
        "Cac listing phu hop voi yeu cau:\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\nThong tin duoc rut ra tu nguon listing kem theo; can kiem tra lai tinh trang va gia truoc khi giao dich."
    ),
    evidence_ids_used=used_ids,
    confidence="high",
)
```

Use equivalent domain filters:

```python
project_evidence = [item for item in evidence if _evidence_domain(item) == "project"]
news_evidence = [item for item in evidence if _evidence_domain(item) == "news"]
legal_evidence = [item for item in evidence if _evidence_domain(item) == "legal"]
```

For `run_legal_agent`, never use `domain="property"` evidence. If `legal_evidence` is empty, return:

```python
return _agent_result(
    agent_name="legal_advisor",
    status="no_evidence",
    content=(
        "Chua co bang chung phap ly de ket luan tinh trang phap ly. "
        "Thong tin phap ly do nguoi dang listing khai bao chi nen xem la thong tin chua xac minh. "
        "Vui long doi chieu van ban hien hanh hoac hoi chuyen gia phap ly truoc khi thuc hien."
    ),
    confidence="low",
    warnings=[_warning("insufficient_legal_evidence", "legal", "Legal evidence is missing.")],
    missing_evidence=["legal"],
)
```

- [ ] **Step 5: Update investment agent**

In `run_investment_agent`, split evidence:

```python
property_evidence = [item for item in evidence if _evidence_domain(item) == "property"]
market_evidence = [item for item in evidence if _evidence_domain(item) == "market"]
project_evidence = [item for item in evidence if _evidence_domain(item) == "project"]
news_evidence = [item for item in evidence if _evidence_domain(item) == "news"]
used_evidence = [*property_evidence, *market_evidence, *project_evidence, *news_evidence]
used_ids = [value for item in used_evidence if (value := _evidence_id(item))]
warnings = [_warning("not_financial_advice", "market", "This is not financial advice.")]
missing = []
status = "completed"
if not market_evidence:
    warnings.append(
        _warning(
            "investment_market_data_missing",
            "market",
            "Market aggregate evidence is not available for this query.",
        )
    )
    missing.append("market")
    status = "partial" if property_evidence else "no_evidence"
if not property_evidence:
    missing.append("property")
    status = "no_evidence"
content = (
    "Nhan dinh dau tu nay khong phai loi khuyen tai chinh; can tu tham dinh dong tien, phap ly va kha nang vay."
)
if property_evidence:
    content += "\nBang chung listing lien quan:\n" + "\n".join(
        f"- {_describe_evidence(item)}" for item in property_evidence
    )
if market_evidence:
    content += "\nDu lieu thi truong lien quan:\n" + "\n".join(
        f"- {_describe_evidence(item)}" for item in market_evidence
    )
return _agent_result(
    agent_name="investment_advisor",
    status=status,
    content=content,
    evidence_ids_used=used_ids,
    confidence="medium" if used_ids else "low",
    warnings=warnings,
    missing_evidence=missing,
)
```

- [ ] **Step 6: Update specialist node to resolve evidence IDs**

In `agent_service/graph/nodes.py`, replace:

```python
evidence = state.get("evidence", {})
```

with:

```python
evidence_by_id = state.get("evidence_by_id", {})
evidence_for_agent = state.get("evidence_for_agent", {})
```

Before calling each runner:

```python
assigned_evidence = [
    evidence_by_id[evidence_id].model_dump(mode="python")
    for evidence_id in evidence_for_agent.get(agent, [])
    if evidence_id in evidence_by_id
]
```

Pass `assigned_evidence` as `evidence`.

- [ ] **Step 7: Run specialist tests**

Run:

```powershell
pytest backend\tests\test_agent_specialists.py backend\tests\test_agent_graph_core.py -q
```

Expected: PASS. If older tests assert numeric confidence, update those tests to accept `"high"`, `"medium"`, or `"low"` because the design rejects uncalibrated probabilities.

- [ ] **Step 8: Commit specialist updates**

Run:

```powershell
git add agent_service\agents\specialists.py agent_service\graph\nodes.py backend\tests\test_agent_specialists.py backend\tests\test_agent_graph_core.py
git commit -m "feat: ground specialists on assigned evidence"
```

---

### Task 7: Add Market Metric Skipping And Readiness Behavior

**Files:**
- Modify: `agent_service/graph/retrieval_planner.py`
- Modify: `agent_service/tools/market.py`
- Test: `backend/tests/test_agent_retrieval_planner.py`

- [ ] **Step 1: Add failing tests for market readiness and skip**

Append to `backend/tests/test_agent_retrieval_planner.py`:

```python
@pytest.mark.asyncio
async def test_market_task_skips_when_city_filter_missing():
    state = _state(
        "Tìm căn hộ Quận 7 dưới 5 tỷ, có tiềm năng đầu tư không?",
        ["investment_advisor", "property_search"],
    )
    task = RetrievalTask(
        task_id="market_lookup_1",
        domain="market",
        tool="lookup_market_metrics",
        query=state["request"].message,
        filters={"district": "Quan 7", "property_type": "Can ho"},
        retrieved_for=["investment_advisor"],
    )

    update = await execute_retrieval_plan([task], state)

    result = update["retrieval_results"]["market_lookup_1"]
    assert result.status == "skipped"
    assert result.skip_reason == "investment_market_data_missing"
    assert result.warnings[0].code == "investment_market_data_missing"
```

- [ ] **Step 2: Run the focused test and verify failure**

Run:

```powershell
pytest backend\tests\test_agent_retrieval_planner.py::test_market_task_skips_when_city_filter_missing -q
```

Expected: FAIL because market tasks are not handled by `execute_retrieval_plan()`.

- [ ] **Step 3: Add market task planning only when useful**

In `build_retrieval_plan()`, after property task planning, add:

```python
if "investment_advisor" in agents and caps["market"]["market_aggregate_ready"]:
    has_market_inputs = bool(listing_filters.get("city"))
    if has_market_inputs:
        plan.append(
            RetrievalTask(
                task_id="market_lookup_1",
                domain="market",
                tool="lookup_market_metrics",
                query=query,
                filters=listing_filters,
                retrieved_for=["investment_advisor"],
                depends_on=[],
                dependency_mode="none",
                top_k=10,
                rerank_top_k=None,
            )
        )
```

This keeps the mixed acceptance query without city on a partial investment path rather than inventing a market metric.

- [ ] **Step 4: Execute market tasks with skip behavior**

In `execute_retrieval_plan()`, before the `_run_hybrid_tool()` branch, add:

```python
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
        retrieval_results[task.task_id] = RetrievalResult(
            task_id=task.task_id,
            status="skipped",
            evidence_ids=[],
            duration_ms=round((time.perf_counter() - task_started) * 1000),
            warnings=[warning],
            skip_reason="investment_market_data_missing",
        )
        trace_events.append({"event": "retrieval_task_skipped", "task_id": task.task_id})
        continue
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
```

Keep the rest of the existing success, empty, and failure handling after this branch.

- [ ] **Step 5: Normalize market records**

Update `normalize_record_to_evidence()` source type mapping and facts branch:

```python
if task.domain == "market":
    source_type = "market_metric"
    source_identity = str(record.get("source_identity") or f"market:{evidence_index}")
    source = AgentSource(
        type="market_metric",
        domain="market",
        id=source_identity,
        title=str(record.get("metric") or "Market metric"),
        url=None,
        snippet=f"{record.get('metric')}: {record.get('value')} {record.get('unit')}",
        location=record.get("location"),
        score=None,
        metadata={
            "source_identity": source_identity,
            "metric": record.get("metric"),
            "period": record.get("period"),
        },
    )
    return Evidence(
        evidence_id=f"ev_{task.task_id}_{evidence_index}",
        retrieval_task_id=task.task_id,
        domain="market",
        source_type="market_metric",
        source_identity=source_identity,
        record=record,
        facts={
            key: value
            for key, value in {
                "metric": record.get("metric"),
                "value": record.get("value"),
                "unit": record.get("unit"),
                "location": record.get("location"),
                "property_type": record.get("property_type"),
                "period": record.get("period"),
            }.items()
            if value is not None
        },
        source=source,
        matched_chunks=[],
        retrieved_for=task.retrieved_for,
        assigned_to=assigned_to,
        warnings=[],
    )
```

- [ ] **Step 6: Run planner tests**

Run:

```powershell
pytest backend\tests\test_agent_retrieval_planner.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit market handling**

Run:

```powershell
git add agent_service\graph\retrieval_planner.py agent_service\tools\market.py backend\tests\test_agent_retrieval_planner.py
git commit -m "feat: handle market metric retrieval readiness"
```

---

### Task 8: Validate Used Evidence In Synthesizer

**Files:**
- Modify: `agent_service/graph/nodes.py`
- Test: `backend/tests/test_agent_graph_core.py`

- [ ] **Step 1: Add synthesizer validation tests**

Append to `backend/tests/test_agent_graph_core.py`:

```python
from agent_service.contracts import Evidence, MatchedChunk, StructuredWarning


def test_synthesizer_exposes_only_valid_used_evidence():
    valid_source = AgentSource(
        type="listing",
        domain="property",
        id="listing:p-1",
        title="Căn hộ A",
        metadata={"source_identity": "listing:p-1"},
    )
    unused_source = AgentSource(
        type="listing",
        domain="property",
        id="listing:p-2",
        title="Căn hộ B",
        metadata={"source_identity": "listing:p-2"},
    )
    evidence_by_id = {
        "ev_valid": Evidence(
            evidence_id="ev_valid",
            retrieval_task_id="search_property_1",
            domain="property",
            source_type="listing",
            source_identity="listing:p-1",
            record={},
            facts={"title": "Căn hộ A"},
            source=valid_source,
            matched_chunks=[MatchedChunk(text="chunk A")],
            retrieved_for=["property_search"],
            assigned_to=["property_search"],
        ),
        "ev_unused": Evidence(
            evidence_id="ev_unused",
            retrieval_task_id="search_property_1",
            domain="property",
            source_type="listing",
            source_identity="listing:p-2",
            record={},
            facts={"title": "Căn hộ B"},
            source=unused_source,
            retrieved_for=["property_search"],
            assigned_to=["property_search"],
        ),
    }
    state = {
        "request": AgentChatRequest(
            request_id="req-synth-valid",
            message="Tim can ho",
            session_id="session-1",
        ),
        "agents_to_run": ["property_search"],
        "evidence_by_id": evidence_by_id,
        "evidence_for_agent": {"property_search": ["ev_valid", "ev_unused"]},
        "agent_results": {
            "property_search": {
                "content": "Căn hộ A phù hợp.",
                "evidence_ids_used": ["ev_valid", "ev_missing"],
                "warnings": [],
                "sources": [],
            }
        },
        "trace_steps": [],
        "warnings": [],
    }

    result = synthesizer_node(state)

    assert [source.id for source in result["sources"]] == ["listing:p-1"]
    warning_codes = [
        warning.code if hasattr(warning, "code") else warning.get("code")
        for warning in result["warnings"]
    ]
    assert "invalid_evidence_reference" in warning_codes
    assert result["trace_steps"][-1]["output"]["used_evidence_ids"] == ["ev_valid"]


def test_synthesizer_rejects_unassigned_evidence_id():
    source = AgentSource(type="article", domain="legal", id="article:1")
    evidence = Evidence(
        evidence_id="ev_legal",
        retrieval_task_id="search_legal_1",
        domain="legal",
        source_type="article",
        source_identity="article:1",
        record={},
        facts={},
        source=source,
        assigned_to=["legal_advisor"],
    )
    state = {
        "request": AgentChatRequest(
            request_id="req-synth-unassigned",
            message="Tim can ho",
            session_id="session-1",
        ),
        "agents_to_run": ["property_search"],
        "evidence_by_id": {"ev_legal": evidence},
        "evidence_for_agent": {"property_search": []},
        "agent_results": {
            "property_search": {
                "content": "Bad citation.",
                "evidence_ids_used": ["ev_legal"],
                "warnings": [],
                "sources": [],
            }
        },
        "trace_steps": [],
        "warnings": [],
    }

    result = synthesizer_node(state)

    assert result["sources"] == []
    assert any(
        (warning.code if hasattr(warning, "code") else warning.get("code"))
        == "invalid_evidence_reference"
        for warning in result["warnings"]
    )
```

- [ ] **Step 2: Run synthesizer tests and verify failure**

Run:

```powershell
pytest backend\tests\test_agent_graph_core.py::test_synthesizer_exposes_only_valid_used_evidence backend\tests\test_agent_graph_core.py::test_synthesizer_rejects_unassigned_evidence_id -q
```

Expected: FAIL because synthesizer still trusts `sources` from agents.

- [ ] **Step 3: Add validation helpers in nodes**

In `agent_service/graph/nodes.py`, import `Evidence` and `StructuredWarning`:

```python
from agent_service.contracts import AgentSource, Evidence, MemoryProposal, StructuredWarning
```

Add helpers above `synthesizer_node`:

```python
def _warning(
    code: str,
    domain: str | None,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> StructuredWarning:
    return StructuredWarning(
        code=code,
        domain=domain,
        message=message,
        retryable=False,
        details=details or {},
    )


def _is_evidence_assigned_to_agent(
    *,
    evidence_id: str,
    agent: str,
    evidence: Evidence,
    evidence_for_agent: dict[str, list[str]],
) -> bool:
    return evidence_id in evidence_for_agent.get(agent, []) or agent in evidence.assigned_to


def _collect_valid_used_evidence(
    *,
    agent_results: dict[str, dict[str, Any]],
    agents_to_run: list[str],
    evidence_by_id: dict[str, Evidence],
    evidence_for_agent: dict[str, list[str]],
) -> tuple[list[Evidence], list[StructuredWarning], list[str]]:
    valid: list[Evidence] = []
    warnings: list[StructuredWarning] = []
    used_ids: list[str] = []
    for agent in agents_to_run:
        result = agent_results.get(agent) or {}
        for evidence_id in result.get("evidence_ids_used", []):
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                warnings.append(
                    _warning(
                        "invalid_evidence_reference",
                        None,
                        "Specialist referenced an evidence ID that does not exist.",
                        details={"agent": agent, "evidence_id": evidence_id},
                    )
                )
                continue
            if not _is_evidence_assigned_to_agent(
                evidence_id=evidence_id,
                agent=agent,
                evidence=evidence,
                evidence_for_agent=evidence_for_agent,
            ):
                warnings.append(
                    _warning(
                        "invalid_evidence_reference",
                        evidence.domain,
                        "Specialist referenced evidence that was not assigned to it.",
                        details={"agent": agent, "evidence_id": evidence_id},
                    )
                )
                continue
            if evidence_id not in used_ids:
                valid.append(evidence)
                used_ids.append(evidence_id)
    return valid, warnings, used_ids
```

- [ ] **Step 4: Replace source collection in synthesizer**

In `synthesizer_node`, remove the loop that appends `result.get("sources", [])`.

After collecting `parts` and warnings, add:

```python
evidence_by_id = state.get("evidence_by_id", {})
evidence_for_agent = state.get("evidence_for_agent", {})
used_evidence, evidence_warnings, used_evidence_ids = _collect_valid_used_evidence(
    agent_results=agent_results,
    agents_to_run=list(state.get("agents_to_run", [])),
    evidence_by_id=evidence_by_id,
    evidence_for_agent=evidence_for_agent,
)
warnings.extend(evidence_warnings)

sources_by_identity: dict[str, AgentSource] = {}
for evidence in used_evidence:
    sources_by_identity.setdefault(evidence.source_identity, evidence.source)
sources = list(sources_by_identity.values())
```

Update trace output:

```python
{
    "answer_length": len(final_response),
    "source_count": len(sources),
    "used_evidence_ids": used_evidence_ids,
}
```

- [ ] **Step 5: Preserve provenance in full trace**

In `agent_service/graph/workflow.py`, update `full_trace` construction:

```python
"retrieval_plan": [
    task.model_dump(mode="json") if hasattr(task, "model_dump") else task
    for task in result.get("retrieval_plan", [])
],
"retrieval_results": {
    key: value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    for key, value in result.get("retrieval_results", {}).items()
},
"evidence": {
    key: value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    for key, value in result.get("evidence_by_id", {}).items()
},
"evidence_for_agent": result.get("evidence_for_agent", {}),
```

Keep existing `steps` and `agent_results`.

- [ ] **Step 6: Run graph tests**

Run:

```powershell
pytest backend\tests\test_agent_graph_core.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit synthesizer validation**

Run:

```powershell
git add agent_service\graph\nodes.py agent_service\graph\workflow.py backend\tests\test_agent_graph_core.py
git commit -m "feat: synthesize sources from validated evidence"
```

---

### Task 9: Add Mixed Query End-To-End Acceptance Test

**Files:**
- Modify: `backend/tests/test_agent_graph_core.py`

- [ ] **Step 1: Add acceptance test**

Append to `backend/tests/test_agent_graph_core.py`:

```python
@pytest.mark.asyncio
async def test_mixed_property_legal_investment_query_uses_shared_evidence(monkeypatch):
    calls = []

    async def fake_run_hybrid_tool(**kwargs):
        calls.append(kwargs["tool_name"])
        if kwargs["parent_type"] == "listing":
            return [
                {
                    "id": 1,
                    "product_id": "p-q7",
                    "title": "Căn hộ 2PN Quận 7",
                    "price": 4.8,
                    "price_text": "4.8 tỷ",
                    "area": 75,
                    "area_text": "75 m2",
                    "district": "Quan 7",
                    "city": "Ho Chi Minh",
                    "legal_status": "Sổ hồng",
                    "url": "https://example.test/listing/p-q7",
                    "matched_chunk": {
                        "id": 10,
                        "chunk_type": "overview",
                        "text": "Căn hộ 2PN Quận 7 dưới 5 tỷ",
                        "distance": 0.2,
                        "rerank_score": 0.93,
                    },
                }
            ]
        if kwargs["parent_type"] == "article":
            assert kwargs["filters"] == {"category": "legal"}
            return [
                {
                    "id": 7,
                    "title": "Điều kiện chuyển nhượng căn hộ",
                    "category": "legal",
                    "url": "legal://transfer",
                    "citation": {"doc_slug": "luat-nha-o", "dieu_number": "32"},
                    "matched_chunk": {
                        "id": 70,
                        "chunk_type": "legal_section",
                        "text": "Quy định về điều kiện chuyển nhượng.",
                        "distance": 0.25,
                        "rerank_score": 0.88,
                    },
                }
            ]
        return []

    monkeypatch.setattr(
        "agent_service.graph.retrieval_planner._run_hybrid_tool",
        fake_run_hybrid_tool,
    )
    monkeypatch.setattr(
        "agent_service.tools.readiness.build_readiness_snapshot",
        lambda: {
            "listings": {"status": "ready", "parent_count": 1, "chunk_count": 1},
            "legal": {"status": "ready", "parent_count": 1, "chunk_count": 1},
            "projects": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "news": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
        },
    )

    request = AgentChatRequest(
        request_id="req-mixed-acceptance",
        message="Tìm căn hộ Quận 7 dưới 5 tỷ, pháp lý ổn và có tiềm năng đầu tư không?",
        session_id="session-1",
    )

    response = await run_agent_graph(request)

    assert set(response.agents_used) >= {
        "property_search",
        "legal_advisor",
        "investment_advisor",
    }
    assert calls.count("search_listings") == 1
    assert calls.count("search_articles") == 1
    trace = response.full_trace
    property_ids = trace["evidence_for_agent"]["property_search"]
    investment_ids = trace["evidence_for_agent"]["investment_advisor"]
    assert property_ids[0] in investment_ids
    warning_codes = [
        warning["code"] if isinstance(warning, dict) else warning
        for warning in response.trace_summary.warnings
    ]
    assert "investment_market_data_missing" in warning_codes
    assert "đủ điều kiện pháp lý" not in response.final_response.lower()
    source_ids = [source.id for source in response.sources]
    used_ids = set()
    for result in trace["agent_results"].values():
        used_ids.update(result.get("evidence_ids_used", []))
    source_identities = {
        trace["evidence"][evidence_id]["source_identity"]
        for evidence_id in used_ids
        if evidence_id in trace["evidence"]
    }
    assert set(source_ids).issubset(source_identities)
```

- [ ] **Step 2: Run acceptance test and verify failure if earlier tasks are incomplete**

Run:

```powershell
pytest backend\tests\test_agent_graph_core.py::test_mixed_property_legal_investment_query_uses_shared_evidence -q
```

Expected: PASS if Tasks 1-8 are complete. If it fails because `market_lookup_1` is not planned for missing city, update the assertion to accept the warning from Investment Agent rather than a market task result. The required behavior is the warning, not a market task.

- [ ] **Step 3: Adjust router keywords only if the acceptance route misses investment**

If `investment_advisor` is not routed for the mixed query, update `KEYWORDS_BY_AGENT["investment_advisor"]` in `agent_service/graph/nodes.py`:

```python
"investment_advisor": ["dau tu", "tiem nang dau tu", "roi", "loi nhuan", "sinh loi", "rental yield"],
```

Run:

```powershell
pytest backend\tests\test_agent_graph_core.py::test_mixed_property_legal_investment_query_uses_shared_evidence -q
```

Expected: PASS.

- [ ] **Step 4: Commit acceptance behavior**

Run:

```powershell
git add agent_service\graph\nodes.py backend\tests\test_agent_graph_core.py
git commit -m "test: cover mixed grounded retrieval graph"
```

---

### Task 10: Backend Boundary And Frontend Type Compatibility

**Files:**
- Modify: `backend/app/services/agent_service/contracts.py`
- Modify: `frontend/lib/types.ts` if needed
- Test: `backend/tests/test_chat_agent_service_integration.py`

- [ ] **Step 1: Add backend client compatibility test**

Append to `backend/tests/test_chat_agent_service_integration.py`:

```python
def test_agent_response_accepts_extended_source_shape():
    response = AgentChatResponse(
        request_id="req-source-shape",
        final_response="Answer",
        agents_used=["property_search"],
        sources=[
            {
                "type": "listing",
                "domain": "property",
                "id": "listing:p-1",
                "product_id": "p-1",
                "title": "Căn hộ A",
                "url": None,
                "snippet": "Căn hộ A Quận 7",
                "location": {"district": "Quan 7"},
                "citation": None,
                "score": 0.91,
                "metadata": {"source_identity": "listing:p-1"},
            }
        ],
        trace_summary=TraceSummary(
            intent="property_search",
            agents=["property_search"],
            source_count=1,
            latency_ms=1,
            warnings=[
                {
                    "code": "investment_market_data_missing",
                    "domain": "market",
                    "message": "Market aggregate evidence is not available.",
                    "retryable": False,
                    "details": {},
                }
            ],
        ),
    )

    assert response.sources[0].id == "listing:p-1"
    assert response.sources[0].domain == "property"
    assert response.trace_summary.warnings[0]["code"] == "investment_market_data_missing"
```

- [ ] **Step 2: Run backend integration tests**

Run:

```powershell
pytest backend\tests\test_chat_agent_service_integration.py -q
```

Expected: PASS after backend mirror contracts match Agent Service contracts.

- [ ] **Step 3: Update frontend type if source fields changed**

If TypeScript complains during lint/build, update `frontend/lib/types.ts` `ChatSource`:

```ts
export interface ChatSource {
  type?: "listing" | "project" | "article" | "market_metric" | "legal_article" | "market_aggregate" | "district_comparison" | "investment_aggregate" | string;
  domain?: "property" | "project" | "news" | "legal" | "market" | string | null;
  id?: number | string;
  product_id?: string | null;
  title?: string | null;
  location?: string | Record<string, unknown> | null;
  snippet?: string | null;
  price_text?: string | null;
  area_text?: string | null;
  published_at?: string | null;
  source?: string | null;
  category?: string | null;
  url?: string | null;
  citation?: {
    doc_slug?: string;
    dieu_number?: number | string;
    khoan_number?: number | string;
  } | string | Record<string, unknown> | null;
  count?: number;
  filters?: Record<string, unknown>;
  items?: Array<Record<string, unknown>>;
  sale?: Record<string, unknown>;
  rent?: Record<string, unknown>;
  rental_yield_percent?: number | null;
  score?: number | null;
  metadata?: Record<string, unknown>;
}
```

- [ ] **Step 4: Run frontend checks only if types changed**

Run from `frontend`:

```powershell
npm.cmd run lint
npm.cmd run build
```

Expected: both commands PASS. If frontend files were not changed, skip this command and record that it was not needed in the final implementation report.

- [ ] **Step 5: Commit boundary compatibility**

Run:

```powershell
git add backend\app\services\agent_service\contracts.py backend\tests\test_chat_agent_service_integration.py frontend\lib\types.ts
git commit -m "feat: support extended agent source contracts"
```

If `frontend/lib/types.ts` was not changed, omit it from `git add`.

---

### Task 11: Full Regression And Cleanup

**Files:**
- Inspect all modified files
- No new feature files unless fixing test failures

- [ ] **Step 1: Run full backend regression**

Run:

```powershell
pytest backend\tests -q
```

Expected: PASS.

- [ ] **Step 2: Run compileall**

Run:

```powershell
python -m compileall backend\app agent_service data_pipeline chatbot crawler
```

Expected: command exits 0.

- [ ] **Step 3: Run diff whitespace check**

Run:

```powershell
git diff --check
```

Expected: no output and exit 0.

- [ ] **Step 4: Inspect final diff**

Run:

```powershell
git diff --stat
git diff -- agent_service backend\app backend\tests frontend\lib\types.ts
```

Expected: diff contains only planned contract, planner, graph, specialist, test, and optional frontend type updates.

- [ ] **Step 5: Run frontend checks if frontend type changed**

Run:

```powershell
cd frontend
npm.cmd run lint
npm.cmd run build
```

Expected: PASS. If `frontend/lib/types.ts` was not changed, skip and state it was not required.

- [ ] **Step 6: Final commit**

If any verification fix remains uncommitted, run:

```powershell
git add agent_service backend\app backend\tests frontend\lib\types.ts
git commit -m "test: verify grounded agent retrieval"
```

If there are no uncommitted planned changes, do not create an empty commit.

---

## Self-Review Checklist

- Spec coverage:
  - Planner-first architecture: Tasks 3, 5.
  - `build_retrieval_plan()` and `execute_retrieval_plan()` testability: Tasks 3, 4, 5.
  - Evidence registry and assignment: Tasks 1, 4, 6.
  - Legal/news article separation: Task 2 and Task 3.
  - Market evidence without new infrastructure: Task 7.
  - Specialist statuses and `evidence_ids_used`: Task 6.
  - Synthesizer source validation: Task 8.
  - Mixed acceptance query: Task 9.
  - Backend/frontend compatibility: Task 10.
  - Definition of done: Task 11.
- No new database tables or migrations are planned.
- `retrieval_planner_node` remains a single LangGraph node.
- Warning storage uses `RetrievalResult.warnings` directly, not `warnings_by_id`.
- `source_identity` is deterministic; request-local IDs remain request-local.
