# Agent RAG Intelligence Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve agent answer quality with optional LLM-assisted routing, query understanding, memory-aware retrieval, LLM specialist synthesis, cost controls, timeout fallback, and stronger grounding checks.

**Architecture:** Add intelligence features inside `agent_service` behind disabled-by-default flags so current deterministic behavior remains the default. Cost tracking, total timeout, and deterministic fallback come before any LLM feature is enabled. Backend changes are limited to additive admin health cost visibility.

**Tech Stack:** LangGraph, FastAPI, Pydantic, pytest, Redis Python client, Google GenAI SDK, existing Agent Service contracts.

---

## Preconditions

- Complete `docs/superpowers/plans/2026-06-11-agent-platform-public-mvp-hardening.md` first.
- Do not enable LLM behavior in production until a currently supported Gemini model is configured through environment variables.
- Do not rely on the current code default `gemini-2.0-flash`.
- Keep all new feature flags disabled by default except cost tracking, which can run passively.

## File Structure

- Modify `agent_service/config.py`: feature flags, model settings, timeout settings, budget settings.
- Modify `agent_service/llm/gemini.py`: structured JSON helper, timeout handling, usage metadata capture.
- Create `agent_service/llm/cost.py`: Redis-backed monthly cost counter and budget decision.
- Modify `agent_service/main.py`: additive Agent Service health fields for cost.
- Modify `backend/app/services/agent_service/client.py`: additive Agent Service health client method.
- Modify `backend/app/routers/admin.py`: add `llm_cost` to `/admin/agent-health`.
- Create `agent_service/graph/router.py`: rule, LLM, and hybrid routing.
- Create `agent_service/graph/query_understanding.py`: rewrite and filter extraction.
- Create `agent_service/graph/memory_filters.py`: safe preference-to-filter merge.
- Modify `agent_service/graph/retrieval_planner.py`: consume `query_understanding`.
- Modify `agent_service/graph/nodes.py`: integrate router, query understanding, memory filters, specialist mode, safety metadata.
- Modify `agent_service/graph/workflow.py`: total timeout wrapper and request-scoped deterministic fallback.
- Modify `agent_service/agents/specialists.py`: expose deterministic fallback helpers where needed.
- Create `agent_service/agents/llm_specialists.py`: optional LLM specialist synthesis.
- Test files:
  - `backend/tests/test_agent_llm_cost_budget.py`
  - `backend/tests/test_agent_total_timeout.py`
  - `backend/tests/test_agent_llm_router.py`
  - `backend/tests/test_agent_query_understanding.py`
  - `backend/tests/test_agent_memory_filters.py`
  - `backend/tests/test_agent_llm_specialists.py`
  - Existing `backend/tests/test_agent_graph_core.py`
  - Existing `backend/tests/test_agent_retrieval_planner.py`
  - Existing `backend/tests/test_agent_specialists.py`
  - Existing `backend/tests/test_agent_evaluation.py`
  - Existing `backend/tests/test_admin_observability.py`

Do not edit listing routers, listing schemas, listing image migrations, crawler modules, pipeline worker, frontend listing pages, or report files.

---

### Task 1: Configuration and Supported Model Guard

**Files:**
- Modify: `agent_service/config.py`
- Test: `backend/tests/test_agent_graph_core.py`

- [ ] **Step 1: Write failing config test**

Add to `backend/tests/test_agent_graph_core.py`:

```python
def test_agent_llm_flags_default_to_deterministic(monkeypatch):
    from agent_service.config import AgentSettings

    monkeypatch.delenv("AGENT_ROUTER_MODE", raising=False)
    monkeypatch.delenv("AGENT_QUERY_REWRITE_ENABLED", raising=False)
    monkeypatch.delenv("AGENT_SPECIALIST_LLM_ENABLED", raising=False)

    settings = AgentSettings()

    assert settings.AGENT_ROUTER_MODE == "rule"
    assert settings.AGENT_QUERY_REWRITE_ENABLED is False
    assert settings.AGENT_MEMORY_FILTERS_ENABLED is False
    assert settings.AGENT_SPECIALIST_LLM_ENABLED is False
```

- [ ] **Step 2: Run failing config test**

```powershell
python -m pytest backend\tests\test_agent_graph_core.py::test_agent_llm_flags_default_to_deterministic -q
```

Expected: FAIL because the new settings are not defined.

- [ ] **Step 3: Add settings**

In `agent_service/config.py`, add:

```python
AGENT_ROUTER_MODE: str = "rule"
AGENT_QUERY_REWRITE_ENABLED: bool = False
AGENT_MEMORY_FILTERS_ENABLED: bool = False
AGENT_SPECIALIST_LLM_ENABLED: bool = False
AGENT_LLM_CONFIDENCE_THRESHOLD: float = 0.65
AGENT_LLM_MAX_REWRITES: int = 3
AGENT_LLM_ROUTER_TIMEOUT_SECONDS: float = 5.0
AGENT_LLM_QUERY_TIMEOUT_SECONDS: float = 5.0
AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS: float = 12.0
AGENT_TOTAL_TIMEOUT_SECONDS: float = 10.0
AGENT_LLM_MONTHLY_BUDGET_USD: float = 100.0
AGENT_LLM_COST_TRACKING_ENABLED: bool = True
```

Add a validator:

```python
@field_validator("AGENT_ROUTER_MODE")
@classmethod
def validate_router_mode(cls, value: str) -> str:
    allowed = {"rule", "llm", "hybrid"}
    if value not in allowed:
        raise ValueError(f"AGENT_ROUTER_MODE must be one of {sorted(allowed)}")
    return value
```

- [ ] **Step 4: Verify config tests pass**

```powershell
python -m pytest backend\tests\test_agent_graph_core.py::test_agent_llm_flags_default_to_deterministic -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add agent_service\config.py backend\tests\test_agent_graph_core.py
git commit -m "feat: add agent intelligence feature flags"
```

---

### Task 2: LLM Cost Tracking and Admin Visibility

**Files:**
- Create: `agent_service/llm/cost.py`
- Modify: `agent_service/llm/gemini.py`
- Modify: `agent_service/main.py`
- Modify: `backend/app/services/agent_service/client.py`
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_agent_llm_cost_budget.py`
- Test: `backend/tests/test_admin_observability.py`

- [ ] **Step 1: Write failing budget tests**

Create `backend/tests/test_agent_llm_cost_budget.py`.

```python
def test_monthly_budget_exceeded_forces_deterministic():
    tracker = InMemoryCostTracker(monthly_budget_usd=1.0)
    tracker.add_estimated_cost("2026-06", 1.25)

    summary = tracker.get_summary("2026-06")

    assert summary["budget_exceeded"] is True
    assert summary["estimated_cost_usd"] == 1.25
```

- [ ] **Step 2: Implement cost tracker**

Create `agent_service/llm/cost.py`.

```python
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class LLMCostSummary:
    month: str
    estimated_cost_usd: float
    monthly_budget_usd: float
    budget_exceeded: bool


def current_month_key(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.strftime("%Y-%m")


def estimate_cost_usd(*, input_tokens: int, output_tokens: int, input_price_per_million: float, output_price_per_million: float) -> float:
    return (input_tokens / 1_000_000 * input_price_per_million) + (
        output_tokens / 1_000_000 * output_price_per_million
    )
```

Add an in-memory implementation for tests and a Redis implementation for runtime:

```python
class InMemoryCostTracker:
    def __init__(self, *, monthly_budget_usd: float) -> None:
        self.monthly_budget_usd = monthly_budget_usd
        self._costs: dict[str, float] = {}

    def add_estimated_cost(self, month: str, amount_usd: float) -> None:
        self._costs[month] = self._costs.get(month, 0.0) + amount_usd

    def get_summary(self, month: str) -> dict:
        total = round(self._costs.get(month, 0.0), 6)
        return {
            "month": month,
            "estimated_cost_usd": total,
            "monthly_budget_usd": self.monthly_budget_usd,
            "budget_exceeded": total >= self.monthly_budget_usd,
        }
```

- [ ] **Step 3: Extend Gemini client to return usage metadata**

In `agent_service/llm/gemini.py`, add a structured result:

```python
@dataclass(frozen=True)
class GeminiResult:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
```

Update `generate_text` to return `GeminiResult` from a new method named `generate_text_with_usage`; keep `generate_text` returning `str` for compatibility:

```python
async def generate_text_with_usage(self, prompt: str, *, timeout_seconds: float | None = None) -> GeminiResult:
    if not self.api_key:
        return GeminiResult(text="")
    timeout = timeout_seconds or self.timeout_seconds
    response = await asyncio.wait_for(asyncio.to_thread(generate_sync), timeout=timeout)
    usage = getattr(response, "usage_metadata", None) or getattr(response, "usageMetadata", None)
    return GeminiResult(
        text=response.text or "",
        input_tokens=getattr(usage, "prompt_token_count", None),
        output_tokens=getattr(usage, "candidates_token_count", None),
    )
```

- [ ] **Step 4: Add health cost summary**

In `agent_service/main.py`, add cost info to `/internal/agent/health`:

```python
return {
    "status": "ok",
    "service": settings.SERVICE_NAME,
    "graph_version": settings.AGENT_GRAPH_VERSION,
    "llm_cost": cost_summary,
}
```

In `backend/app/services/agent_service/client.py`, add:

```python
async def health(self) -> dict:
    headers = {"X-Internal-Agent-Key": self.internal_key}
    async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds), transport=self.transport) as client:
        response = await client.get(f"{self.base_url}/internal/agent/health", headers=headers)
        response.raise_for_status()
        return response.json()
```

In `backend/app/routers/admin.py`, add `llm_cost` to `/admin/agent-health` response while preserving `items`.

- [ ] **Step 5: Verify budget and admin tests**

```powershell
python -m pytest backend\tests\test_agent_llm_cost_budget.py backend\tests\test_admin_observability.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent_service\llm\cost.py agent_service\llm\gemini.py agent_service\main.py backend\app\services\agent_service\client.py backend\app\routers\admin.py backend\tests\test_agent_llm_cost_budget.py backend\tests\test_admin_observability.py
git commit -m "feat: track agent llm cost budget"
```

---

### Task 3: Total Timeout and Request-Scoped Deterministic Fallback

**Files:**
- Modify: `agent_service/graph/state.py`
- Modify: `agent_service/graph/workflow.py`
- Modify: `agent_service/graph/nodes.py`
- Test: `backend/tests/test_agent_total_timeout.py`

- [ ] **Step 1: Write failing timeout test**

Create `backend/tests/test_agent_total_timeout.py`.

```python
async def test_total_timeout_falls_back_deterministically(monkeypatch):
    request = AgentChatRequest(request_id="req-timeout", message="tu van dau tu quan 7")

    async def slow_ainvoke(state):
        await asyncio.sleep(0.2)
        return state

    monkeypatch.setattr("agent_service.graph.workflow.chat_graph.ainvoke", slow_ainvoke)
    monkeypatch.setattr("agent_service.config.AgentSettings.AGENT_TOTAL_TIMEOUT_SECONDS", 0.01, raising=False)

    response = await run_agent_graph(request)

    assert "agent_total_timeout_exceeded" in response.trace_summary.warnings
    assert response.final_response
```

- [ ] **Step 2: Add force deterministic state flag**

In `agent_service/graph/state.py`, include:

```python
force_deterministic: bool
```

Use `state.get("force_deterministic", False)` in nodes.

- [ ] **Step 3: Wrap graph execution**

In `agent_service/graph/workflow.py`:

```python
import asyncio


async def _invoke_graph(request: AgentChatRequest, *, force_deterministic: bool = False) -> dict:
    return await chat_graph.ainvoke(
        {
            "request": request,
            "trace_steps": [],
            "warnings": [],
            "force_deterministic": force_deterministic,
        }
    )
```

Update `run_agent_graph`:

```python
settings = get_agent_settings()
try:
    result = await asyncio.wait_for(
        _invoke_graph(request),
        timeout=settings.AGENT_TOTAL_TIMEOUT_SECONDS,
    )
except asyncio.TimeoutError:
    result = await asyncio.wait_for(
        _invoke_graph(request, force_deterministic=True),
        timeout=settings.AGENT_TOTAL_TIMEOUT_SECONDS,
    )
    result["warnings"] = [*result.get("warnings", []), "agent_total_timeout_exceeded"]
```

- [ ] **Step 4: Force deterministic in router and specialist nodes**

In `agent_service/graph/nodes.py`, when `force_deterministic` is true:

```python
if state.get("force_deterministic", False):
    decision = route_with_rules(state)
else:
    decision = await route_request(state)
```

For specialists:

```python
use_llm = settings.AGENT_SPECIALIST_LLM_ENABLED and not state.get("force_deterministic", False)
```

- [ ] **Step 5: Verify timeout test**

```powershell
python -m pytest backend\tests\test_agent_total_timeout.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent_service\graph\state.py agent_service\graph\workflow.py agent_service\graph\nodes.py backend\tests\test_agent_total_timeout.py
git commit -m "feat: add total agent timeout fallback"
```

---

### Task 4: LLM-Assisted Router

**Files:**
- Create: `agent_service/graph/router.py`
- Modify: `agent_service/graph/nodes.py`
- Test: `backend/tests/test_agent_llm_router.py`
- Test: `backend/tests/test_agent_graph_core.py`

- [ ] **Step 1: Write failing router tests**

Create `backend/tests/test_agent_llm_router.py`.

```python
def test_hybrid_router_keeps_rule_legal_keyword_and_llm_investment():
    def fake_request():
        return AgentChatRequest(
            request_id="req-router",
            message="phap ly va dau tu can ho quan 7",
            session_id="session-1",
        )

    state = {"normalized_query": "phap ly va dau tu can ho quan 7", "request": fake_request()}
    llm_decision = RouterDecision(
        intent="investment_advice",
        agents=["investment_advisor"],
        confidence=0.9,
        filters={},
        needs_clarification=False,
        clarifying_question=None,
        reason="investment language",
        mode="llm",
        warnings=[],
    )

    merged = merge_router_decisions(route_with_rules(state), llm_decision, confidence_threshold=0.65)

    assert "legal_advisor" in merged.agents
    assert "investment_advisor" in merged.agents
```

- [ ] **Step 2: Implement router schemas and rule routing**

Create `agent_service/graph/router.py`.

```python
from pydantic import BaseModel, Field

ALLOWED_AGENTS = {
    "property_search",
    "project_agent",
    "market_analysis",
    "news_agent",
    "legal_advisor",
    "investment_advisor",
}


class RouterDecision(BaseModel):
    intent: str
    agents: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    filters: dict = Field(default_factory=dict)
    needs_clarification: bool = False
    clarifying_question: str | None = None
    reason: str = ""
    mode: str = "rule"
    warnings: list = Field(default_factory=list)
```

Move current keyword logic from `nodes.py` into `route_with_rules(state)`.

- [ ] **Step 3: Implement LLM parsing and hybrid merge**

```python
def sanitize_agents(agents: list[str]) -> tuple[list[str], list[str]]:
    valid = []
    dropped = []
    for agent in agents:
        if agent in ALLOWED_AGENTS and agent not in valid:
            valid.append(agent)
        else:
            dropped.append(agent)
    return valid, dropped


def merge_router_decisions(rule: RouterDecision, llm: RouterDecision, *, confidence_threshold: float) -> RouterDecision:
    agents = list(rule.agents)
    if llm.confidence >= confidence_threshold:
        for agent in llm.agents:
            if agent not in agents:
                agents.append(agent)
    if not agents:
        agents = ["property_search"]
    return RouterDecision(
        intent=rule.intent if len(agents) == 1 else "mixed",
        agents=agents,
        confidence=max(rule.confidence, llm.confidence),
        filters={**llm.filters, **rule.filters},
        mode="hybrid",
        reason=f"rule={rule.reason}; llm={llm.reason}",
        warnings=[*rule.warnings, *llm.warnings],
    )
```

- [ ] **Step 4: Integrate router node**

In `agent_service/graph/nodes.py`, replace inline routing with:

```python
decision = await route_request(state)
return {
    "intent": decision.intent,
    "agents_to_run": decision.agents,
    "routing_filters": decision.filters,
    "trace_steps": _append_trace(state, "router", start_time, decision.model_dump(mode="json")),
}
```

- [ ] **Step 5: Verify router tests**

```powershell
python -m pytest backend\tests\test_agent_llm_router.py backend\tests\test_agent_graph_core.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent_service\graph\router.py agent_service\graph\nodes.py backend\tests\test_agent_llm_router.py backend\tests\test_agent_graph_core.py
git commit -m "feat: add llm-assisted agent router"
```

---

### Task 5: Query Understanding and Retrieval Integration

**Files:**
- Create: `agent_service/graph/query_understanding.py`
- Modify: `agent_service/graph/nodes.py`
- Modify: `agent_service/graph/retrieval_planner.py`
- Test: `backend/tests/test_agent_query_understanding.py`
- Test: `backend/tests/test_agent_retrieval_planner.py`

- [ ] **Step 1: Write failing query understanding tests**

Create `backend/tests/test_agent_query_understanding.py`.

```python
def test_current_query_filter_overrides_llm_inferred_filter():
    deterministic = {"district": "Quan 7"}
    llm = {"district": "Quan 2", "max_price": 5000000000}

    merged = merge_query_filters(deterministic, llm)

    assert merged["district"] == "Quan 7"
    assert merged["max_price"] == 5000000000
```

- [ ] **Step 2: Implement schema and filter merge**

Create `agent_service/graph/query_understanding.py`.

```python
from pydantic import BaseModel, Field

ALLOWED_FILTERS = {
    "listing_type",
    "property_type",
    "city",
    "district",
    "ward",
    "min_price",
    "max_price",
    "min_area",
    "max_area",
    "bedrooms",
}


class QueryUnderstanding(BaseModel):
    original_query: str
    normalized_query: str
    rewritten_query: str
    expanded_queries: list[str] = Field(default_factory=list)
    filters: dict = Field(default_factory=dict)
    inferred_filters: dict = Field(default_factory=dict)
    missing_slots: list[str] = Field(default_factory=list)
    warnings: list = Field(default_factory=list)


def validate_filters(filters: dict) -> dict:
    return {key: value for key, value in filters.items() if key in ALLOWED_FILTERS}


def merge_query_filters(deterministic: dict, inferred: dict) -> dict:
    return {**validate_filters(inferred), **validate_filters(deterministic)}
```

- [ ] **Step 3: Add query understanding node behavior**

In `agent_service/graph/nodes.py`, call query understanding after router:

```python
understanding = await build_query_understanding(state)
return {
    "query_understanding": understanding.model_dump(mode="python"),
    "trace_steps": _append_trace(state, "query_understanding", start_time, understanding.model_dump(mode="json")),
}
```

- [ ] **Step 4: Use rewritten query in retrieval planner**

In `agent_service/graph/retrieval_planner.py`:

```python
understanding = state.get("query_understanding") or {}
semantic_query = understanding.get("rewritten_query") or state["request"].message
filters = understanding.get("filters") or _extract_filters(state["request"].message)
```

Do not issue retrieval tasks for `expanded_queries`; keep them in trace only.

- [ ] **Step 5: Verify query and retrieval tests**

```powershell
python -m pytest backend\tests\test_agent_query_understanding.py backend\tests\test_agent_retrieval_planner.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent_service\graph\query_understanding.py agent_service\graph\nodes.py agent_service\graph\retrieval_planner.py backend\tests\test_agent_query_understanding.py backend\tests\test_agent_retrieval_planner.py
git commit -m "feat: add query understanding for retrieval"
```

---

### Task 6: Memory-Aware Retrieval Filters

**Files:**
- Create: `agent_service/graph/memory_filters.py`
- Modify: `agent_service/graph/nodes.py`
- Test: `backend/tests/test_agent_memory_filters.py`

- [ ] **Step 1: Write failing memory filter tests**

Create `backend/tests/test_agent_memory_filters.py`.

```python
def test_memory_fills_missing_district_without_overriding_query():
    result = derive_memory_filters(
        user_preferences={"preferred_district": "Quan 7"},
        current_filters={},
        query="tim can ho",
    )

    assert result.filters["district"] == "Quan 7"
    assert result.applied_keys == ["preferred_district"]
```

- [ ] **Step 2: Implement memory filter result**

Create `agent_service/graph/memory_filters.py`.

```python
from pydantic import BaseModel, Field


class MemoryFilterResult(BaseModel):
    filters: dict = Field(default_factory=dict)
    applied_keys: list[str] = Field(default_factory=list)
    skipped_keys: list[str] = Field(default_factory=list)
    warnings: list = Field(default_factory=list)


PREFERENCE_TO_FILTER = {
    "preferred_city": "city",
    "preferred_district": "district",
    "preferred_property_type": "property_type",
    "listing_type": "listing_type",
    "bedrooms": "bedrooms",
    "max_budget": "max_price",
    "min_budget": "min_price",
}


def derive_memory_filters(user_preferences: dict, current_filters: dict, query: str) -> MemoryFilterResult:
    filters = dict(current_filters)
    applied = []
    skipped = []
    for pref_key, filter_key in PREFERENCE_TO_FILTER.items():
        value = user_preferences.get(pref_key)
        if value is None:
            continue
        if filter_key in current_filters:
            skipped.append(pref_key)
            continue
        filters[filter_key] = value
        applied.append(pref_key)
    return MemoryFilterResult(filters=filters, applied_keys=applied, skipped_keys=skipped)
```

- [ ] **Step 3: Integrate memory filters**

In `agent_service/graph/nodes.py`, after query understanding:

```python
if settings.AGENT_MEMORY_FILTERS_ENABLED:
    memory_result = derive_memory_filters(
        state["request"].user_preferences,
        understanding.filters,
        state["request"].message,
    )
    understanding.filters = memory_result.filters
```

Record `applied_keys` and `skipped_keys` in trace.

- [ ] **Step 4: Verify memory tests**

```powershell
python -m pytest backend\tests\test_agent_memory_filters.py backend\tests\test_agent_graph_core.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add agent_service\graph\memory_filters.py agent_service\graph\nodes.py backend\tests\test_agent_memory_filters.py backend\tests\test_agent_graph_core.py
git commit -m "feat: add memory-aware retrieval filters"
```

---

### Task 7: Optional LLM Specialist Synthesis

**Files:**
- Create: `agent_service/agents/llm_specialists.py`
- Modify: `agent_service/agents/specialists.py`
- Modify: `agent_service/graph/nodes.py`
- Test: `backend/tests/test_agent_llm_specialists.py`
- Test: `backend/tests/test_agent_specialists.py`

- [x] **Step 1: Write failing LLM specialist fallback tests**

Create `backend/tests/test_agent_llm_specialists.py`.

```python
async def test_invalid_llm_specialist_json_falls_back(monkeypatch):
    async def fake_deterministic_runner(query, evidence, preferences, readiness):
        return {
            "status": "no_evidence",
            "content": "Chua co du bang chung de tra loi.",
            "evidence_ids_used": [],
            "warnings": [],
        }

    async def invalid_json(prompt: str):
        return {}

    result = await run_llm_or_deterministic_specialist(
        agent_name="investment_advisor",
        deterministic_runner=fake_deterministic_runner,
        query="co nen mua khong",
        evidence=[],
        preferences={},
        readiness={},
        generate_json=invalid_json,
    )

    assert result["status"] in {"completed", "no_evidence"}
    assert "llm_specialist_invalid_json" in result["warnings"]
```

- [x] **Step 2: Implement common output schema**

Create `agent_service/agents/llm_specialists.py`.

```python
from pydantic import BaseModel, Field


class LLMSpecialistOutput(BaseModel):
    agent_name: str
    status: str
    content: str
    claims: list[dict] = Field(default_factory=list)
    evidence_ids_used: list[str] = Field(default_factory=list)
    confidence: float | str | None = None
    warnings: list = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
```

- [x] **Step 3: Implement LLM wrapper with deterministic fallback**

```python
async def run_llm_or_deterministic_specialist(
    *,
    agent_name: str,
    deterministic_runner,
    query: str,
    evidence: list[dict],
    preferences: dict,
    readiness: dict,
    generate_json,
) -> dict:
    deterministic = await deterministic_runner(
        query=query,
        evidence=evidence,
        preferences=preferences,
        readiness=readiness,
    )
    parsed = await generate_json(build_specialist_prompt(agent_name, query, evidence, preferences))
    try:
        output = LLMSpecialistOutput.model_validate(parsed)
    except Exception:
        deterministic["warnings"] = [*deterministic.get("warnings", []), "llm_specialist_invalid_json"]
        return deterministic
    if not set(output.evidence_ids_used).issubset({item["id"] for item in evidence if "id" in item}):
        deterministic["warnings"] = [*deterministic.get("warnings", []), "llm_specialist_invalid_evidence"]
        return deterministic
    return output.model_dump(mode="python")
```

- [x] **Step 4: Integrate specialist node**

In `agent_service/graph/nodes.py`:

```python
if settings.AGENT_SPECIALIST_LLM_ENABLED and not state.get("force_deterministic", False):
    agent_results[agent] = await run_llm_or_deterministic_specialist(...)
else:
    agent_results[agent] = await runner(...)
```

- [x] **Step 5: Verify specialist tests**

```powershell
python -m pytest backend\tests\test_agent_llm_specialists.py backend\tests\test_agent_specialists.py -q
```

Expected: PASS.

- [x] **Step 6: Commit**

```powershell
git add agent_service\agents\llm_specialists.py agent_service\agents\specialists.py agent_service\graph\nodes.py backend\tests\test_agent_llm_specialists.py backend\tests\test_agent_specialists.py
git commit -m "feat: add optional llm specialist synthesis"
```

---

### Task 8: Stronger Grounding, Safety, and Eval Metadata

**Files:**
- Modify: `agent_service/graph/nodes.py`
- Modify: `agent_service/graph/workflow.py`
- Test: `backend/tests/test_agent_evaluation.py`
- Test: `backend/tests/test_agent_graph_core.py`

- [x] **Step 1: Write failing safety metadata test**

In `backend/tests/test_agent_evaluation.py`:

```python
async def test_trace_records_intelligence_feature_modes():
    response = await run_agent_graph(AgentChatRequest(request_id="req-meta", message="thi truong quan 7"))

    metadata = response.full_trace["intelligence"]

    assert metadata["router_mode"] in {"rule", "llm", "hybrid"}
    assert "query_rewrite_enabled" in metadata
    assert "specialist_llm_enabled" in metadata
```

- [x] **Step 2: Add intelligence metadata to full trace**

In `agent_service/graph/workflow.py`:

```python
settings = get_agent_settings()
intelligence_metadata = {
    "router_mode": settings.AGENT_ROUTER_MODE,
    "query_rewrite_enabled": settings.AGENT_QUERY_REWRITE_ENABLED,
    "memory_filters_enabled": settings.AGENT_MEMORY_FILTERS_ENABLED,
    "specialist_llm_enabled": settings.AGENT_SPECIALIST_LLM_ENABLED,
    "model_name": settings.GEMINI_MODEL,
    "prompt_version": settings.AGENT_PROMPT_VERSION,
}
```

Include it under:

```python
"intelligence": intelligence_metadata
```

- [x] **Step 3: Strengthen claim validation**

In `agent_service/graph/nodes.py`, update safety validation:

```python
def _claim_requires_evidence(claim: dict) -> bool:
    return claim.get("type") not in {"caveat", "disclaimer", "missing_evidence"}


def _invalid_claim_ratio(claims: list[dict], valid_ids: set[str]) -> float:
    checked = [claim for claim in claims if _claim_requires_evidence(claim)]
    if not checked:
        return 0.0
    invalid = [
        claim for claim in checked
        if not set(claim.get("evidence_ids", [])).intersection(valid_ids)
    ]
    return len(invalid) / len(checked)
```

If ratio is above `0.30`, add `agent_answer_missing_valid_evidence` and use deterministic fallback content for that agent.

- [x] **Step 4: Verify safety and eval tests**

```powershell
python -m pytest backend\tests\test_agent_evaluation.py backend\tests\test_agent_graph_core.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

```powershell
git add agent_service\graph\nodes.py agent_service\graph\workflow.py backend\tests\test_agent_evaluation.py backend\tests\test_agent_graph_core.py
git commit -m "feat: record intelligence trace metadata"
```

---

### Task 9: Intelligence Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run focused intelligence tests**

```powershell
python -m pytest backend\tests\test_agent_llm_router.py backend\tests\test_agent_query_understanding.py backend\tests\test_agent_memory_filters.py backend\tests\test_agent_llm_specialists.py backend\tests\test_agent_llm_cost_budget.py backend\tests\test_agent_total_timeout.py backend\tests\test_agent_graph_core.py backend\tests\test_agent_retrieval_planner.py backend\tests\test_agent_specialists.py backend\tests\test_agent_evaluation.py -q
```

Expected: PASS.

- [ ] **Step 2: Compile Python packages**

```powershell
python -m compileall agent_service backend\app
```

Expected: no syntax errors.

- [ ] **Step 3: Verify deterministic default**

Run a graph test with all LLM env vars unset:

```powershell
python -m pytest backend\tests\test_agent_graph_core.py::test_agent_llm_flags_default_to_deterministic -q
```

Expected: PASS and no live Gemini call.

- [ ] **Step 4: Check compose config**

```powershell
docker compose config --services
```

Expected: command exits 0.

- [ ] **Step 5: Commit verification docs if changed**

If no files changed, do not create an empty commit. If documentation changed:

```powershell
git add docs
git commit -m "docs: record intelligence verification"
```
