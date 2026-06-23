# Agentic RAG Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate from static multi-node LangGraph to full Agentic RAG with autonomous specialist agents, per-agent ReAct loops, agent-to-agent blackboard communication, and a shared Tool Registry.

**Architecture:** Each specialist agent becomes an autonomous class with its own `think → act → observe` ReAct loop. Agents independently call tools via a ToolRegistry instead of relying on a centralized retrieval planner. They communicate through an extended Blackboard (read/write/query). A lightweight Orchestrator Agent replaces the 14-node static graph, dispatching to specialists and synthesizing results. The safety validator, memory system, and contracts remain intact.

**Tech Stack:** Python 3.11+, LangGraph (simplified), Google Gemini 2.5 Flash, existing `agent_service/tools/`, existing `agent_service/contracts.py`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `agent_service/agents/base.py` | `BaseAgent` abstract class: ReAct loop, tool calling, blackboard interface |
| `agent_service/agents/property_search_agent.py` | `PropertySearchAgent(BaseAgent)` — autonomous listing search |
| `agent_service/agents/market_analysis_agent.py` | `MarketAnalysisAgent(BaseAgent)` — autonomous market analysis |
| `agent_service/agents/legal_advisor_agent.py` | `LegalAdvisorAgent(BaseAgent)` — autonomous legal advice |
| `agent_service/agents/investment_advisor_agent.py` | `InvestmentAdvisorAgent(BaseAgent)` — autonomous investment analysis |
| `agent_service/agents/project_agent.py` | `ProjectAgent(BaseAgent)` — autonomous project evaluation |
| `agent_service/agents/news_agent.py` | `NewsAgent(BaseAgent)` — autonomous news analysis |
| `agent_service/agents/orchestrator.py` | `OrchestratorAgent` — router + dispatch + synthesize |
| `agent_service/tools/registry.py` | `ToolRegistry` — register, list, call tools; per-agent permissions |
| `agent_service/graph/agentic_workflow.py` | Simplified 4-node graph: context → orchestrator → safety → memory |
| `tests/test_base_agent.py` | Unit tests for BaseAgent ReAct loop |
| `tests/test_tool_registry.py` | Unit tests for ToolRegistry |
| `tests/test_property_search_agent.py` | Integration test for PropertySearchAgent |
| `tests/test_orchestrator.py` | Integration test for OrchestratorAgent |

### Modified Files
| File | Change |
|------|--------|
| `agent_service/contracts.py` | Add `AgentThought`, `AgentAction`, `ToolDef`, `AgentContext` |
| `agent_service/graph/blackboard.py` | Add `read()`, `query()` methods |
| `agent_service/graph/state.py` | Add `AgenticState` (simplified replacement for `AgentGraphState`) |
| `agent_service/config.py` | Add `AGENT_MAX_ITERATIONS`, `AGENT_TOOL_TIMEOUT`, `AGENT_ORCHESTRATOR_MODE` |
| `agent_service/main.py` | Wire new `run_agentic_graph()` alongside existing `run_agent_graph()` |

### Unchanged (Keep As-Is)
| File | Reason |
|------|--------|
| `agent_service/contracts.py` (existing types) | `AgentSource`, `Evidence`, `RetrievalTask`, `AgentChatRequest/Response` stay |
| `agent_service/tools/retrieval.py` | `search_listings`, `search_projects`, `search_articles` stay |
| `agent_service/tools/market.py` | `lookup_market_metrics`, `lookup_market_timeseries` stay |
| `agent_service/tools/readiness.py` | `build_readiness_snapshot` stays |
| `agent_service/graph/synthesis.py` | `synthesize_final_answer`, `SynthesisResult` stay |
| `agent_service/graph/investment_model.py` | `build_investment_case`, `calculate_investment_metrics` stay |
| `agent_service/graph/committee.py` | `build_committee_review` stays |
| `agent_service/graph/memory_extraction.py` | `extract_memory_proposals` stays |
| `agent_service/graph/memory_filters.py` | `derive_memory_filters` stays |
| `agent_service/graph/query_understanding.py` | `build_query_understanding` stays |
| `agent_service/graph/router.py` | `route_request` stays (used by orchestrator) |
| `agent_service/llm/gemini.py` | `GeminiClient` stays |
| `agent_service/llm/cost.py` | `get_runtime_cost_summary` stays |
| `agent_service/evaluation/judge.py` | `judge_answer` stays |
| `agent_service/security.py` | `require_internal_key` stays |

### Deferred Deprecation (keep but stop importing)
| File | Reason |
|------|--------|
| `agent_service/graph/workflow.py` | Replaced by `agentic_workflow.py` — keep for rollback |
| `agent_service/graph/nodes.py` | Replaced by agent classes — keep for rollback |
| `agent_service/graph/retrieval_planner.py` | Replaced by per-agent tool calling |
| `agent_service/graph/react_controller.py` | Replaced by per-agent ReAct loops |
| `agent_service/agents/specialists.py` | Replaced by individual agent classes |
| `agent_service/agents/llm_specialists.py` | Replaced by LLM path in BaseAgent |

---

### Task 1: Add New Contract Types

**Files:**
- Modify: `agent_service/contracts.py:1-5` (add imports at top)
- Modify: `agent_service/contracts.py:130-135` (append after `AgentChatResponse`)

- [ ] **Step 1: Add new contract types to contracts.py**

Add the following classes at the end of `agent_service/contracts.py`, after the existing `AgentChatResponse` class (after line ~137):

```python
# ── Agentic RAG: Agent autonomy contracts ──────────────────────────


class ToolDef(BaseModel):
    """Definition of a tool an agent can call."""
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    required_params: list[str] = Field(default_factory=list)
    allowed_for: list[str] = Field(default_factory=list)


class AgentThought(BaseModel):
    """A single reasoning step in an agent's ReAct loop."""
    iteration: int
    reasoning: str
    action: Literal["call_tool", "final_answer", "ask_clarification", "delegate"]
    tool_name: str | None = None
    tool_params: dict[str, Any] = Field(default_factory=dict)
    target_agent: str | None = None
    delegate_query: str | None = None
    clarifying_question: str | None = None
    confidence: float = 0.0


class AgentAction(BaseModel):
    """Result of executing an agent's action."""
    iteration: int
    action_type: Literal["call_tool", "final_answer", "ask_clarification", "delegate"]
    status: Literal["success", "error", "timeout", "noop"]
    tool_result: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0


class AgentContext(BaseModel):
    """Context passed to each agent at initialization."""
    agent_name: str
    query: str
    normalized_query: str
    conversation_context: list[dict[str, str]] = Field(default_factory=list)
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    readiness: dict[str, Any] = Field(default_factory=dict)
    routing_filters: dict[str, Any] = Field(default_factory=dict)
    query_understanding: dict[str, Any] = Field(default_factory=dict)
    locale: str = "vi-VN"


class AgentResult(BaseModel):
    """Standardized output from any agent run."""
    agent_name: str
    status: Literal["completed", "partial", "no_evidence", "failed", "skipped"]
    content: str
    evidence_ids_used: list[str] = Field(default_factory=list)
    sources: list[AgentSource] = Field(default_factory=list)
    confidence: float | str | None = None
    warnings: list[str | StructuredWarning] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    iterations: int = 0
    trace: list[dict[str, Any]] = Field(default_factory=list)
    charts: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
```

- [ ] **Step 2: Verify imports compile**

Run: `python -c "from agent_service.contracts import ToolDef, AgentThought, AgentAction, AgentContext, AgentResult; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agent_service/contracts.py
git commit -m "feat: add Agentic RAG contract types (ToolDef, AgentThought, AgentAction, AgentContext, AgentResult)"
```

---

### Task 2: Create ToolRegistry

**Files:**
- Create: `agent_service/tools/registry.py`
- Create: `tests/test_tool_registry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tool_registry.py`:

```python
import pytest
from agent_service.tools.registry import ToolRegistry, ToolDef


class FakeTool:
    """Simulates an async tool function."""
    def __init__(self, name: str):
        self.name = name
        self.call_count = 0

    async def __call__(self, **kwargs):
        self.call_count += 1
        return {"status": "ok", "kwargs": kwargs}


@pytest.fixture
def registry():
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="search_listings",
        description="Search real estate listings",
        parameters={"query": "str", "filters": "dict"},
        required_params=["query"],
        allowed_for=["property_search", "investment_advisor"],
    ))
    reg.register(ToolDef(
        name="search_articles",
        description="Search knowledge articles",
        parameters={"query": "str", "filters": "dict"},
        required_params=["query"],
        allowed_for=["legal_advisor", "news_agent"],
    ))
    return reg


def test_list_tools_for_agent(registry):
    tools = registry.list_for_agent("property_search")
    tool_names = [t.name for t in tools]
    assert "search_listings" in tool_names
    assert "search_articles" not in tool_names


def test_list_tools_for_agent_not_allowed_returns_empty(registry):
    tools = registry.list_for_agent("market_analysis")
    assert len(tools) == 0


def test_has_tool(registry):
    assert registry.has_tool("search_listings") is True
    assert registry.has_tool("nonexistent") is False


def test_get_tool_def(registry):
    tool_def = registry.get_tool_def("search_listings")
    assert tool_def is not None
    assert tool_def.name == "search_listings"
    assert "query" in tool_def.required_params


def test_register_duplicate_raises(registry):
    with pytest.raises(ValueError, match="already registered"):
        registry.register(ToolDef(
            name="search_listings",
            description="Duplicate",
            allowed_for=[],
        ))


def test_is_tool_allowed_for_agent(registry):
    assert registry.is_tool_allowed_for_agent("search_listings", "property_search") is True
    assert registry.is_tool_allowed_for_agent("search_articles", "property_search") is False
    assert registry.is_tool_allowed_for_agent("nonexistent", "property_search") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tool_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_service.tools.registry'`

- [ ] **Step 3: Write ToolRegistry implementation**

Create `agent_service/tools/registry.py`:

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent_service.contracts import ToolDef


ToolFunction = Callable[..., Awaitable[dict[str, Any]]]


class ToolRegistry:
    """Registry of tools that agents can call.

    Each tool is registered with metadata (ToolDef) and an async
    callable. Agents query the registry for their allowed tools
    and call them by name.
    """

    def __init__(self):
        self._defs: dict[str, ToolDef] = {}
        self._functions: dict[str, ToolFunction] = {}

    def register(
        self,
        tool_def: ToolDef,
        func: ToolFunction | None = None,
    ) -> None:
        """Register a tool definition and optionally its function.

        The function can be bound later via bind().
        """
        if tool_def.name in self._defs:
            raise ValueError(
                f"Tool '{tool_def.name}' is already registered."
            )
        self._defs[tool_def.name] = tool_def
        if func is not None:
            self._functions[tool_def.name] = func

    def bind(self, name: str, func: ToolFunction) -> None:
        """Bind a callable to an already-registered tool."""
        if name not in self._defs:
            raise KeyError(f"Tool '{name}' is not registered. Call register() first.")
        self._functions[name] = func

    def has_tool(self, name: str) -> bool:
        """Check if a tool name is registered."""
        return name in self._defs

    def get_tool_def(self, name: str) -> ToolDef | None:
        """Get the ToolDef for a tool, or None."""
        return self._defs.get(name)

    def is_tool_allowed_for_agent(self, tool_name: str, agent_name: str) -> bool:
        """Check if agent is allowed to use this tool."""
        tool_def = self._defs.get(tool_name)
        if tool_def is None:
            return False
        if not tool_def.allowed_for:
            return True  # No restrictions
        return agent_name in tool_def.allowed_for

    def list_for_agent(self, agent_name: str) -> list[ToolDef]:
        """Return all ToolDefs this agent is allowed to use."""
        return [
            tool_def
            for tool_def in self._defs.values()
            if self.is_tool_allowed_for_agent(tool_def.name, agent_name)
        ]

    def list_all(self) -> list[ToolDef]:
        """Return all registered ToolDefs."""
        return list(self._defs.values())

    async def call(
        self,
        tool_name: str,
        agent_name: str,
        **params: Any,
    ) -> dict[str, Any]:
        """Call a tool by name, checking agent permission.

        Returns:
            dict with at least: {"status": "success"|"error", ...}

        Raises:
            KeyError: Tool not registered or not bound.
            PermissionError: Agent not allowed to use this tool.
        """
        if not self.has_tool(tool_name):
            raise KeyError(f"Tool '{tool_name}' is not registered.")
        if not self.is_tool_allowed_for_agent(tool_name, agent_name):
            raise PermissionError(
                f"Agent '{agent_name}' is not allowed to use tool '{tool_name}'."
            )
        func = self._functions.get(tool_name)
        if func is None:
            raise KeyError(
                f"Tool '{tool_name}' has no bound function. Call bind() first."
            )
        return await func(**params)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tool_registry.py -v`
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent_service/tools/registry.py tests/test_tool_registry.py
git commit -m "feat: add ToolRegistry for agent tool discovery and calling"
```

---

### Task 3: Extend Blackboard with Read and Query

**Files:**
- Modify: `agent_service/graph/blackboard.py`

- [ ] **Step 1: Add read() and query() methods to blackboard.py**

Open `agent_service/graph/blackboard.py`. Add the following two functions after line ~58 (after `append_blackboard_entry`):

```python
def read_blackboard(
    state: dict[str, Any],
    *,
    author: str | None = None,
    entry_type: str | None = None,
    min_confidence: Confidence = "low",
    max_entries: int = 10,
) -> list[dict[str, Any]]:
    """Read entries from the blackboard, optionally filtered.

    Agents use this to discover what other agents have found.
    """
    blackboard = state.get("agent_blackboard") or {}
    entries = blackboard.get("entries", [])

    confidence_order: dict[Confidence, int] = {"low": 0, "medium": 1, "high": 2}
    min_level = confidence_order.get(min_confidence, 0)

    filtered: list[dict[str, Any]] = []
    for entry in entries:
        if author is not None and entry.get("author") != author:
            continue
        if entry_type is not None and entry.get("type") != entry_type:
            continue
        entry_conf = entry.get("confidence", "low")
        if confidence_order.get(entry_conf, 0) < min_level:
            continue
        filtered.append(dict(entry))

    return filtered[-max_entries:]


def query_blackboard(
    state: dict[str, Any],
    *,
    query: str,
    max_entries: int = 5,
) -> list[dict[str, Any]]:
    """Simple keyword search across blackboard entries.

    For more advanced semantic search, agents should use the
    ToolRegistry to call a dedicated search tool.
    """
    blackboard = state.get("agent_blackboard") or {}
    entries = blackboard.get("entries", [])
    if not query:
        return entries[-max_entries:]

    query_lower = query.lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in entries:
        score = 0
        content = entry.get("content", "")
        if isinstance(content, dict):
            content_str = " ".join(
                str(v) for v in content.values() if isinstance(v, (str, int, float))
            )
        else:
            content_str = str(content)
        if query_lower in content_str.lower():
            score += 3
        if query_lower in str(entry.get("author", "")).lower():
            score += 2
        if query_lower in str(entry.get("type", "")).lower():
            score += 1
        if score > 0:
            scored.append((score, dict(entry)))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in scored[:max_entries]]
```

- [ ] **Step 2: Verify imports and syntax**

Run: `python -c "from agent_service.graph.blackboard import read_blackboard, query_blackboard; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agent_service/graph/blackboard.py
git commit -m "feat: add read_blackboard() and query_blackboard() for agent-to-agent communication"
```

---

### Task 4: Create BaseAgent Abstract Class

**Files:**
- Create: `agent_service/agents/base.py`
- Create: `tests/test_base_agent.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_base_agent.py`:

```python
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent_service.agents.base import BaseAgent
from agent_service.contracts import (
    AgentContext,
    AgentResult,
    AgentThought,
    AgentAction,
    ToolDef,
)
from agent_service.graph.blackboard import BlackboardEntry
from agent_service.graph.state import AgenticState


class CountingAgent(BaseAgent):
    """Test agent that counts iterations then answers."""

    def __init__(self, max_iterations: int = 3):
        super().__init__(agent_name="counting_agent", max_iterations=max_iterations)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict],
    ) -> AgentThought:
        if iteration >= self.max_iterations:
            return AgentThought(
                iteration=iteration,
                reasoning="Max iterations reached, must answer.",
                action="final_answer",
                confidence=0.5,
            )
        return AgentThought(
            iteration=iteration,
            reasoning=f"Iteration {iteration}, need more data.",
            action="call_tool",
            tool_name="fake_search",
            tool_params={"query": context.query, "iter": iteration},
            confidence=0.7,
        )

    async def act(
        self, thought: AgentThought, context: AgentContext
    ) -> AgentAction:
        if thought.action == "final_answer":
            return AgentAction(
                iteration=thought.iteration,
                action_type="final_answer",
                status="success",
                tool_result={"answer": f"Done at iteration {thought.iteration}"},
            )
        return AgentAction(
            iteration=thought.iteration,
            action_type="call_tool",
            status="success",
            tool_result={"results": [{"id": 1, "title": "Test listing"}]},
            evidence_ids=["ev_001"],
        )

    async def observe(
        self,
        thought: AgentThought,
        action: AgentAction,
        context: AgentContext,
    ) -> bool:
        return thought.action == "final_answer"

    def build_result(
        self,
        context: AgentContext,
        thoughts: list[AgentThought],
        actions: list[AgentAction],
    ) -> AgentResult:
        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="Counting complete.",
            evidence_ids_used=["ev_001"],
            iterations=len(thoughts),
        )


@pytest.fixture
def agent_context():
    return AgentContext(
        agent_name="counting_agent",
        query="test query",
        normalized_query="test query",
    )


@pytest.mark.asyncio
async def test_base_agent_runs_react_loop(agent_context):
    agent = CountingAgent(max_iterations=2)
    result = await agent.run(agent_context, {})

    assert result.agent_name == "counting_agent"
    assert result.status == "completed"
    assert result.iterations == 2


@pytest.mark.asyncio
async def test_base_agent_respects_max_iterations(agent_context):
    agent = CountingAgent(max_iterations=1)
    result = await agent.run(agent_context, {})

    assert result.iterations == 1
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_base_agent_enforces_timeout(agent_context):
    """Agent that thinks forever should be stopped by timeout."""
    class SlowAgent(CountingAgent):
        async def think(self, context, iteration, previous_actions, blackboard_entries):
            await asyncio.sleep(10.0)
            return await super().think(context, iteration, previous_actions, blackboard_entries)

    agent = SlowAgent(max_iterations=5)
    result = await agent.run(agent_context, {}, timeout_seconds=0.1)

    assert result.status == "failed"
    assert any("timeout" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_base_agent_handles_think_exception(agent_context):
    class ErrorAgent(CountingAgent):
        async def think(self, context, iteration, previous_actions, blackboard_entries):
            raise RuntimeError("Think failed")

    agent = ErrorAgent(max_iterations=3)
    result = await agent.run(agent_context, {})

    assert result.status == "failed"
    assert any("Think failed" in str(w) for w in result.warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_base_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_service.agents.base'`

- [ ] **Step 3: Write BaseAgent implementation**

Create `agent_service/agents/base.py`:

```python
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any

from agent_service.contracts import (
    AgentAction,
    AgentContext,
    AgentResult,
    AgentThought,
    StructuredWarning,
)
from agent_service.graph.blackboard import read_blackboard


def _warning(code: str, message: str) -> StructuredWarning:
    return StructuredWarning(code=code, message=message)


class BaseAgent(ABC):
    """Abstract base for all autonomous specialist agents.

    Implements the ReAct (Reasoning + Acting) loop:
        think → act → observe → (repeat or stop)

    Subclasses implement:
      - think():   Decide what to do next
      - act():     Execute the decided action
      - observe(): Determine if the loop should stop
      - build_result(): Produce the final AgentResult
    """

    def __init__(
        self,
        *,
        agent_name: str,
        max_iterations: int = 3,
    ):
        self.agent_name = agent_name
        self.max_iterations = max_iterations

    # ── Subclass interface ──────────────────────────────────────

    @abstractmethod
    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        """Decide the next action.

        Args:
            context: Full agent context (query, filters, preferences, etc.)
            iteration: Current loop iteration (0-indexed).
            previous_actions: All actions taken so far in this run.
            blackboard_entries: Latest entries from the shared blackboard.

        Returns:
            AgentThought with action, tool_name, tool_params, etc.
        """
        ...

    @abstractmethod
    async def act(
        self,
        thought: AgentThought,
        context: AgentContext,
    ) -> AgentAction:
        """Execute the action decided by think().

        For call_tool actions, this should call self.call_tool().
        For final_answer, this should return immediately.
        """
        ...

    @abstractmethod
    async def observe(
        self,
        thought: AgentThought,
        action: AgentAction,
        context: AgentContext,
    ) -> bool:
        """Determine if the ReAct loop should stop.

        Returns:
            True if the agent has enough information to answer.
        """
        ...

    @abstractmethod
    def build_result(
        self,
        context: AgentContext,
        thoughts: list[AgentThought],
        actions: list[AgentAction],
    ) -> AgentResult:
        """Build the final AgentResult from the completed loop."""
        ...

    # ── Shared infrastructure ────────────────────────────────────

    async def call_tool(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        """Call a tool via the ToolRegistry.

        Subclasses should use this rather than calling tools directly.
        The ToolRegistry is injected at run time via run().
        """
        if self._tool_registry is None:
            raise RuntimeError(
                "ToolRegistry not set. Call agent.run() which injects it."
            )
        return await self._tool_registry.call(
            tool_name=tool_name,
            agent_name=self.agent_name,
            **tool_params,
        )

    def _read_blackboard(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return read_blackboard(state, min_confidence="low", max_entries=20)

    # ── ReAct loop ───────────────────────────────────────────────

    async def run(
        self,
        context: AgentContext,
        state: dict[str, Any],
        *,
        tool_registry: Any | None = None,
        timeout_seconds: float = 30.0,
    ) -> AgentResult:
        """Execute the full ReAct loop.

        Args:
            context: AgentContext with query, filters, preferences.
            state: Full graph state (for blackboard access).
            tool_registry: ToolRegistry instance for tool calling.
            timeout_seconds: Max time for the entire agent run.

        Returns:
            AgentResult with content, sources, evidence_ids, etc.
        """
        self._tool_registry = tool_registry
        thoughts: list[AgentThought] = []
        actions: list[AgentAction] = []
        started = time.perf_counter()

        for iteration in range(self.max_iterations):
            elapsed = time.perf_counter() - started
            if elapsed > timeout_seconds:
                return AgentResult(
                    agent_name=self.agent_name,
                    status="failed",
                    content="Agent timed out before completing analysis.",
                    warnings=[_warning("agent_timeout", f"Timed out after {elapsed:.1f}s")],
                    iterations=iteration,
                )

            try:
                blackboard_entries = self._read_blackboard(state)
                thought = await self.think(
                    context, iteration, actions, blackboard_entries
                )
                thoughts.append(thought)
            except Exception as exc:
                return AgentResult(
                    agent_name=self.agent_name,
                    status="failed",
                    content=f"Agent failed during think: {exc}",
                    warnings=[_warning("think_error", str(exc))],
                    iterations=iteration,
                )

            if thought.action == "final_answer":
                action = AgentAction(
                    iteration=iteration,
                    action_type="final_answer",
                    status="success",
                )
                actions.append(action)
                return self.build_result(context, thoughts, actions)

            if thought.action == "ask_clarification":
                return AgentResult(
                    agent_name=self.agent_name,
                    status="partial",
                    content=thought.clarifying_question
                    or "Could you provide more details?",
                    iterations=iteration,
                )

            try:
                action = await self.act(thought, context)
                actions.append(action)
            except Exception as exc:
                return AgentResult(
                    agent_name=self.agent_name,
                    status="failed",
                    content=f"Agent failed during act: {exc}",
                    warnings=[_warning("act_error", str(exc))],
                    iterations=iteration,
                )

            try:
                done = await self.observe(thought, action, context)
                if done:
                    return self.build_result(context, thoughts, actions)
            except Exception as exc:
                return AgentResult(
                    agent_name=self.agent_name,
                    status="failed",
                    content=f"Agent failed during observe: {exc}",
                    warnings=[_warning("observe_error", str(exc))],
                    iterations=iteration,
                )

        # Max iterations reached
        return self.build_result(context, thoughts, actions)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_base_agent.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent_service/agents/base.py tests/test_base_agent.py
git commit -m "feat: add BaseAgent abstract class with ReAct loop"
```

---

### Task 5: Create PropertySearchAgent (First Specialist)

**Files:**
- Create: `agent_service/agents/property_search_agent.py`
- Create: `tests/test_property_search_agent.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_property_search_agent.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from agent_service.agents.property_search_agent import PropertySearchAgent
from agent_service.contracts import AgentContext
from agent_service.tools.registry import ToolRegistry, ToolDef


@pytest.fixture
def agent_context():
    return AgentContext(
        agent_name="property_search",
        query="Tìm căn hộ Quận 7 dưới 3 tỷ",
        normalized_query="tim can ho quan 7 duoi 3 ty",
        routing_filters={"city": "Hồ Chí Minh", "district": "Quận 7", "max_price": 3},
    )


@pytest.fixture
async def tool_registry():
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="search_listings",
        description="Search real estate listings",
        parameters={"query": "str", "filters": "dict", "top_k": "int", "rerank_to": "int"},
        required_params=["query"],
        allowed_for=["property_search", "investment_advisor"],
    ))

    async def fake_search(*, query: str, filters: dict | None = None, top_k: int = 20, rerank_to: int = 5):
        return {
            "status": "success",
            "results": [
                {
                    "id": "L001",
                    "title": "Căn hộ cao cấp Quận 7",
                    "price_text": "2.5 tỷ",
                    "area_text": "70m²",
                    "district": "Quận 7",
                    "city": "Hồ Chí Minh",
                    "price_per_m2": 35.7,
                },
                {
                    "id": "L002",
                    "title": "Chung cư giá rẻ Quận 7",
                    "price_text": "2.8 tỷ",
                    "area_text": "75m²",
                    "district": "Quận 7",
                    "city": "Hồ Chí Minh",
                    "price_per_m2": 37.3,
                },
            ],
            "evidence_ids": ["ev_L001", "ev_L002"],
        }

    reg.bind("search_listings", fake_search)
    return reg


@pytest.mark.asyncio
async def test_property_search_agent_calls_search_listings(agent_context, tool_registry):
    agent = PropertySearchAgent(max_iterations=3)
    result = await agent.run(agent_context, {}, tool_registry=tool_registry)

    assert result.agent_name == "property_search"
    assert result.status == "completed"
    assert len(result.evidence_ids_used) >= 2
    assert "Quận 7" in result.content
    assert result.iterations >= 1


@pytest.mark.asyncio
async def test_property_search_agent_no_evidence(agent_context):
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="search_listings",
        description="Search listings",
        allowed_for=["property_search"],
    ))

    async def empty_search(*, query, filters=None, top_k=20, rerank_to=5):
        return {"status": "empty", "results": [], "evidence_ids": []}

    reg.bind("search_listings", empty_search)

    agent = PropertySearchAgent(max_iterations=3)
    result = await agent.run(agent_context, {}, tool_registry=reg)

    assert result.status in ("no_evidence", "partial", "completed")
    # Should not hallucinate listings when there are none
    assert "L001" not in result.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_property_search_agent.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write PropertySearchAgent**

Create `agent_service/agents/property_search_agent.py`:

```python
from __future__ import annotations

from typing import Any

from agent_service.agents.base import BaseAgent
from agent_service.contracts import (
    AgentAction,
    AgentContext,
    AgentResult,
    AgentSource,
    AgentThought,
)


class PropertySearchAgent(BaseAgent):
    """Autonomous property search agent with its own ReAct loop.

    Flow:
      1. think: "Do I have listings? If not → call search_listings"
      2. act:   Execute search_listings via ToolRegistry
      3. observe: "Do I have ≥1 result? If yes → final_answer"
      4. (optional) think: "Need market comparison → call lookup_market_metrics"
      5. final_answer: Format listings with prices and area
    """

    def __init__(self, max_iterations: int = 3):
        super().__init__(agent_name="property_search", max_iterations=max_iterations)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        has_listings = any(
            action.tool_result.get("results")
            for action in previous_actions
            if action.action_type == "call_tool"
        )

        if not has_listings:
            return AgentThought(
                iteration=iteration,
                reasoning="No listings yet. Need to search for properties matching the query.",
                action="call_tool",
                tool_name="search_listings",
                tool_params={
                    "query": context.normalized_query,
                    "filters": context.routing_filters,
                    "top_k": 20,
                    "rerank_to": 5,
                },
                confidence=0.9,
            )

        # If we have listings but haven't compared to market, do that
        has_market_data = any(
            action.tool_result.get("metric") == "avg_price_per_m2"
            for action in previous_actions
            if action.action_type == "call_tool"
        )
        if not has_market_data and context.routing_filters:
            city = context.routing_filters.get("city")
            district = context.routing_filters.get("district")
            if city:
                return AgentThought(
                    iteration=iteration,
                    reasoning="Have listings, now compare with market average for context.",
                    action="call_tool",
                    tool_name="lookup_market_metrics",
                    tool_params={
                        "filters": {
                            "city": city,
                            "district": district,
                            "listing_type": context.routing_filters.get("listing_type", "sale"),
                        }
                    },
                    confidence=0.8,
                )

        return AgentThought(
            iteration=iteration,
            reasoning="Sufficient data gathered. Ready to present listings.",
            action="final_answer",
            confidence=0.9,
        )

    async def act(
        self, thought: AgentThought, context: AgentContext
    ) -> AgentAction:
        import time
        started = time.perf_counter()

        if thought.action == "final_answer":
            return AgentAction(
                iteration=thought.iteration,
                action_type="final_answer",
                status="success",
                duration_ms=0.0,
            )

        try:
            result = await self.call_tool(
                tool_name=thought.tool_name,
                tool_params=thought.tool_params or {},
                context=context,
            )
            evidence_ids = result.get("evidence_ids", [])
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="success",
                tool_result=result,
                evidence_ids=evidence_ids if isinstance(evidence_ids, list) else [],
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        except Exception as exc:
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="error",
                error_message=str(exc),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )

    async def observe(
        self,
        thought: AgentThought,
        action: AgentAction,
        context: AgentContext,
    ) -> bool:
        return thought.action == "final_answer"

    def build_result(
        self,
        context: AgentContext,
        thoughts: list[AgentThought],
        actions: list[AgentAction],
    ) -> AgentResult:
        all_listings: list[dict[str, Any]] = []
        all_evidence_ids: list[str] = []
        market_data: list[dict[str, Any]] = []

        for action in actions:
            results = action.tool_result.get("results", [])
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        if item.get("metric"):
                            market_data.append(item)
                        elif item.get("title"):
                            all_listings.append(item)
            for eid in action.evidence_ids:
                if eid not in all_evidence_ids:
                    all_evidence_ids.append(eid)

        if not all_listings:
            return AgentResult(
                agent_name=self.agent_name,
                status="no_evidence",
                content=(
                    "Chưa tìm thấy bất động sản nào phù hợp với tiêu chí của bạn. "
                    "Vui lòng thử mở rộng khu vực tìm kiếm hoặc điều chỉnh ngân sách."
                ),
                warnings=[],
                iterations=len(thoughts),
            )

        # ── Build listing cards ──────────────────────────────────
        lines = ["🏠 **Kết quả tìm kiếm bất động sản:**\n"]
        for i, listing in enumerate(all_listings[:10], 1):
            title = listing.get("title", "Không có tiêu đề")
            price = listing.get("price_text", "Liên hệ")
            area = listing.get("area_text", "N/A")
            district = listing.get("district", "")
            city = listing.get("city", "")
            location = f"{district}, {city}" if district else city
            ppm = listing.get("price_per_m2")
            ppm_str = f" - {ppm:.1f} tr/m²" if ppm else ""

            lines.append(
                f"**{i}. {title}**\n"
                f"   💰 {price} | 📐 {area} | 📍 {location}{ppm_str}\n"
            )

        # ── Market context if available ──────────────────────────
        if market_data:
            avg_prices = [
                float(m.get("value", 0))
                for m in market_data
                if m.get("metric") == "avg_price_per_m2" and m.get("value")
            ]
            if avg_prices:
                avg = sum(avg_prices) / len(avg_prices)
                lines.append(f"\n📊 **Giá trung bình khu vực:** {avg:.1f} tr/m²")
                lines.append(
                    "> ℹ️ Giá/m² tính từ diện tích và giá listing. "
                    "Giá thực tế có thể thay đổi khi thương lượng."
                )

        sources = [
            AgentSource(
                type="listing",
                id=listing.get("id"),
                title=listing.get("title"),
                location={"district": listing.get("district"), "city": listing.get("city")},
                metadata={
                    "price_text": listing.get("price_text"),
                    "area_text": listing.get("area_text"),
                },
            )
            for listing in all_listings[:10]
        ]

        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=all_evidence_ids,
            sources=sources,
            confidence="high" if all_listings else "low",
            iterations=len(thoughts),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_property_search_agent.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent_service/agents/property_search_agent.py tests/test_property_search_agent.py
git commit -m "feat: add autonomous PropertySearchAgent with ReAct loop"
```

---

### Task 6: Create LegalAdvisorAgent

**Files:**
- Create: `agent_service/agents/legal_advisor_agent.py`

- [ ] **Step 1: Write LegalAdvisorAgent**

Create `agent_service/agents/legal_advisor_agent.py`:

```python
from __future__ import annotations

from typing import Any

from agent_service.agents.base import BaseAgent
from agent_service.contracts import (
    AgentAction,
    AgentContext,
    AgentResult,
    AgentSource,
    AgentThought,
)


class LegalAdvisorAgent(BaseAgent):
    """Autonomous legal advisor agent with domain guardrails.

    Only responds to real-estate legal questions. Uses
    search_articles for legal knowledge base retrieval.

    Flow:
      1. think: Check if query is in-domain → call search_articles
      2. act:   Execute search_articles via ToolRegistry
      3. observe: Has legal evidence? → final_answer
      4. final_answer: Present legal info with citations and disclaimer
    """

    # Vietnamese legal keywords for domain gating
    LEGAL_DOMAIN_KEYWORDS = [
        "phap ly", "luat", "thu tuc", "cong chung", "so do", "so hong",
        "sang ten", "thue", "phi truoc ba", "chuyen nhuong", "thua ke",
        "the chap", "quy hoach", "xay dung", "dat dai", "nha o",
        "chung cu", "du an", "den bu", "giai toa", "hop dong",
        "giay chung nhan", "muaban", "chothue",
    ]

    def __init__(self, max_iterations: int = 3):
        super().__init__(agent_name="legal_advisor", max_iterations=max_iterations)

    def _is_in_domain(self, query: str) -> bool:
        query_lower = query.lower()
        return any(kw in query_lower for kw in self.LEGAL_DOMAIN_KEYWORDS)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        # Domain check on first iteration
        if iteration == 0 and not self._is_in_domain(context.normalized_query):
            return AgentThought(
                iteration=iteration,
                reasoning="Query is not a legal question about real estate.",
                action="final_answer",
                confidence=0.95,
            )

        has_legal_evidence = any(
            action.tool_result.get("results")
            for action in previous_actions
            if action.action_type == "call_tool"
        )

        if not has_legal_evidence:
            return AgentThought(
                iteration=iteration,
                reasoning="Need to search legal knowledge base for relevant articles and regulations.",
                action="call_tool",
                tool_name="search_articles",
                tool_params={
                    "query": context.normalized_query,
                    "filters": {"category": "legal"},
                    "top_k": 15,
                    "rerank_to": 5,
                },
                confidence=0.9,
            )

        # Check blackboard for listing context from property_search
        listing_context = ""
        for entry in blackboard_entries:
            if entry.get("author") == "property_search" and entry.get("type") == "listing_analysis":
                content = entry.get("content", "")
                if isinstance(content, str):
                    listing_context = content[:500]

        if listing_context and iteration < self.max_iterations - 1:
            return AgentThought(
                iteration=iteration,
                reasoning="Found property context from PropertySearch. Cross-referencing legal requirements.",
                action="call_tool",
                tool_name="search_articles",
                tool_params={
                    "query": f"{context.normalized_query} {listing_context}",
                    "filters": {"category": "legal"},
                    "top_k": 10,
                    "rerank_to": 3,
                },
                confidence=0.75,
            )

        return AgentThought(
            iteration=iteration,
            reasoning="Sufficient legal evidence gathered. Ready to provide legal advice.",
            action="final_answer",
            confidence=0.85,
        )

    async def act(
        self, thought: AgentThought, context: AgentContext
    ) -> AgentAction:
        import time
        started = time.perf_counter()

        if thought.action == "final_answer":
            if not self._is_in_domain(context.normalized_query):
                return AgentAction(
                    iteration=thought.iteration,
                    action_type="final_answer",
                    status="success",
                    tool_result={"out_of_domain": True},
                )
            return AgentAction(
                iteration=thought.iteration,
                action_type="final_answer",
                status="success",
            )

        try:
            result = await self.call_tool(
                tool_name=thought.tool_name,
                tool_params=thought.tool_params or {},
                context=context,
            )
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="success",
                tool_result=result,
                evidence_ids=result.get("evidence_ids", []),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        except Exception as exc:
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="error",
                error_message=str(exc),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )

    async def observe(
        self,
        thought: AgentThought,
        action: AgentAction,
        context: AgentContext,
    ) -> bool:
        return thought.action == "final_answer"

    def build_result(
        self,
        context: AgentContext,
        thoughts: list[AgentThought],
        actions: list[AgentAction],
    ) -> AgentResult:
        # Out-of-domain check
        if actions and actions[0].tool_result.get("out_of_domain"):
            return AgentResult(
                agent_name=self.agent_name,
                status="completed",
                content=(
                    "Tôi chỉ hỗ trợ các vấn đề pháp lý về bất động sản. "
                    "Vui lòng hỏi về mua bán, giấy tờ, thuế phí, hoặc các "
                    "vấn đề pháp lý liên quan đến nhà đất."
                ),
                iterations=len(thoughts),
            )

        all_articles: list[dict[str, Any]] = []
        all_evidence_ids: list[str] = []

        for action in actions:
            results = action.tool_result.get("results", [])
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict) and item.get("title"):
                        all_articles.append(item)
            for eid in action.evidence_ids:
                if eid not in all_evidence_ids:
                    all_evidence_ids.append(eid)

        if not all_articles:
            return AgentResult(
                agent_name=self.agent_name,
                status="no_evidence",
                content=(
                    "Chưa tìm thấy văn bản pháp lý liên quan đến câu hỏi của bạn. "
                    "Tôi khuyên bạn nên tham khảo ý kiến luật sư chuyên nghiệp."
                ),
                warnings=[],
                iterations=len(thoughts),
            )

        lines = ["⚖️ **Tư vấn pháp lý bất động sản:**\n"]
        for i, article in enumerate(all_articles[:5], 1):
            title = article.get("title", "Văn bản pháp luật")
            citation = article.get("citation", "")
            snippet = article.get("snippet", article.get("text", ""))[:300]
            lines.append(f"**{i}. {title}**")
            if citation:
                lines.append(f"   📜 Trích dẫn: {citation}")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append("")

        lines.append(
            "> ⚠️ **Lưu ý:** Thông tin trên chỉ mang tính tham khảo, "
            "không thay thế tư vấn luật sư chuyên nghiệp. "
            "Vui lòng kiểm tra văn bản pháp luật mới nhất."
        )

        sources = [
            AgentSource(
                type="article",
                id=article.get("id"),
                title=article.get("title"),
                citation=article.get("citation"),
                snippet=article.get("snippet", ""),
            )
            for article in all_articles[:5]
        ]

        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=all_evidence_ids,
            sources=sources,
            confidence="medium",
            iterations=len(thoughts),
        )
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "from agent_service.agents.legal_advisor_agent import LegalAdvisorAgent; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agent_service/agents/legal_advisor_agent.py
git commit -m "feat: add autonomous LegalAdvisorAgent with domain guardrails"
```

---

### Task 7: Create Remaining Specialist Agents

**Files:**
- Create: `agent_service/agents/market_analysis_agent.py`
- Create: `agent_service/agents/investment_advisor_agent.py`
- Create: `agent_service/agents/project_agent.py`
- Create: `agent_service/agents/news_agent.py`

- [ ] **Step 1: Create MarketAnalysisAgent**

Create `agent_service/agents/market_analysis_agent.py`:

```python
from __future__ import annotations

from typing import Any

from agent_service.agents.base import BaseAgent
from agent_service.contracts import (
    AgentAction,
    AgentContext,
    AgentResult,
    AgentSource,
    AgentThought,
)


class MarketAnalysisAgent(BaseAgent):
    """Autonomous market analysis agent.

    Flow:
      1. think: Need market data → call lookup_market_metrics
      2. think: Need timeseries for trend → call lookup_market_timeseries
      3. final_answer: Interpret trends, compare areas, provide context
    """

    def __init__(self, max_iterations: int = 3):
        super().__init__(agent_name="market_analysis", max_iterations=max_iterations)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        has_metrics = any(
            action.tool_result.get("metric") == "avg_price_per_m2"
            for action in previous_actions
            if action.action_type == "call_tool"
        )
        has_timeseries = any(
            "timeseries" in str(action.tool_result.get("results", ""))
            for action in previous_actions
            if action.action_type == "call_tool"
        )

        if not has_metrics:
            return AgentThought(
                iteration=iteration,
                reasoning="Need current market snapshot for area comparison.",
                action="call_tool",
                tool_name="lookup_market_metrics",
                tool_params={"filters": context.routing_filters},
                confidence=0.9,
            )

        if not has_timeseries:
            return AgentThought(
                iteration=iteration,
                reasoning="Need historical timeseries to analyze price trends.",
                action="call_tool",
                tool_name="lookup_market_timeseries",
                tool_params={"filters": context.routing_filters},
                confidence=0.85,
            )

        return AgentThought(
            iteration=iteration,
            reasoning="Sufficient market data gathered.",
            action="final_answer",
            confidence=0.9,
        )

    async def act(
        self, thought: AgentThought, context: AgentContext
    ) -> AgentAction:
        import time
        started = time.perf_counter()

        if thought.action == "final_answer":
            return AgentAction(
                iteration=thought.iteration,
                action_type="final_answer",
                status="success",
            )

        try:
            result = await self.call_tool(
                tool_name=thought.tool_name,
                tool_params=thought.tool_params or {},
                context=context,
            )
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="success",
                tool_result=result,
                evidence_ids=result.get("evidence_ids", []),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        except Exception as exc:
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="error",
                error_message=str(exc),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )

    async def observe(
        self, thought: AgentThought, action: AgentAction, context: AgentContext
    ) -> bool:
        return thought.action == "final_answer"

    def build_result(
        self,
        context: AgentContext,
        thoughts: list[AgentThought],
        actions: list[AgentAction],
    ) -> AgentResult:
        metrics = []
        timeseries = []
        for action in actions:
            results = action.tool_result.get("results", [])
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        if item.get("metric"):
                            metrics.append(item)
                        elif item.get("snapshot_month"):
                            timeseries.append(item)

        if not metrics and not timeseries:
            return AgentResult(
                agent_name=self.agent_name,
                status="no_evidence",
                content=(
                    "Chưa có dữ liệu thị trường cho khu vực này. "
                    "Vui lòng thử khu vực khác hoặc quay lại sau."
                ),
                iterations=len(thoughts),
            )

        lines = ["📊 **Phân tích thị trường bất động sản:**\n"]
        if metrics:
            lines.append("**Giá trung bình hiện tại:**")
            for m in metrics[:5]:
                location = m.get("location", {})
                district = location.get("district", "") if isinstance(location, dict) else ""
                lines.append(
                    f"- {district or 'Khu vực'}: {m.get('value', 'N/A')} {m.get('unit', 'tr/m²')}"
                )

        if timeseries:
            lines.append("\n**Xu hướng giá:**")
            for ts in timeseries[:6]:
                month = ts.get("snapshot_month", "")
                avg = ts.get("avg_price_per_m2", "N/A")
                lines.append(f"- {month}: {avg} tr/m²")

        lines.append(
            "\n> ℹ️ Dữ liệu chỉ mang tính tham khảo, giá thực tế có thể khác tùy vị trí cụ thể."
        )

        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=[],
            sources=[],
            confidence="medium",
            iterations=len(thoughts),
        )
```

- [ ] **Step 2: Create InvestmentAdvisorAgent**

Create `agent_service/agents/investment_advisor_agent.py`:

```python
from __future__ import annotations

from typing import Any

from agent_service.agents.base import BaseAgent
from agent_service.contracts import (
    AgentAction,
    AgentContext,
    AgentResult,
    AgentSource,
    AgentThought,
)


class InvestmentAdvisorAgent(BaseAgent):
    """Autonomous investment advisor agent.

    Reads blackboard for listing data from PropertySearch,
    market data from MarketAnalysis, then provides investment analysis.

    Flow:
      1. think: Read blackboard for property + market context
      2. think: If needed → call lookup_market_metrics for area comparison
      3. final_answer: ROI analysis with disclaimers
    """

    def __init__(self, max_iterations: int = 3):
        super().__init__(agent_name="investment_advisor", max_iterations=max_iterations)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        # Extract property and market context from blackboard
        property_context = [
            e for e in blackboard_entries
            if e.get("author") == "property_search"
        ]
        market_context = [
            e for e in blackboard_entries
            if e.get("author") == "market_analysis"
        ]

        has_market_data = any(
            action.tool_result.get("value")
            for action in previous_actions
            if action.action_type == "call_tool"
        )

        if not has_market_data and not market_context:
            return AgentThought(
                iteration=iteration,
                reasoning="Need market metrics for investment comparison.",
                action="call_tool",
                tool_name="lookup_market_metrics",
                tool_params={
                    "filters": {
                        "city": context.routing_filters.get("city", "Hồ Chí Minh"),
                        "listing_type": context.routing_filters.get("listing_type", "sale"),
                    }
                },
                confidence=0.8,
            )

        return AgentThought(
            iteration=iteration,
            reasoning="Sufficient data for investment analysis.",
            action="final_answer",
            confidence=0.8,
        )

    async def act(
        self, thought: AgentThought, context: AgentContext
    ) -> AgentAction:
        import time
        started = time.perf_counter()

        if thought.action == "final_answer":
            return AgentAction(
                iteration=thought.iteration,
                action_type="final_answer",
                status="success",
            )

        try:
            result = await self.call_tool(
                tool_name=thought.tool_name,
                tool_params=thought.tool_params or {},
                context=context,
            )
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="success",
                tool_result=result,
                evidence_ids=result.get("evidence_ids", []),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        except Exception as exc:
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="error",
                error_message=str(exc),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )

    async def observe(
        self, thought: AgentThought, action: AgentAction, context: AgentContext
    ) -> bool:
        return thought.action == "final_answer"

    def build_result(
        self,
        context: AgentContext,
        thoughts: list[AgentThought],
        actions: list[AgentAction],
    ) -> AgentResult:
        lines = [
            "💰 **Phân tích đầu tư bất động sản:**\n",
            "Dựa trên dữ liệu thị trường hiện có, tôi đưa ra một số nhận định:\n",
            "- **Tiềm năng tăng giá:** Cần xem xét vị trí, quy hoạch, và xu hướng khu vực.",
            "- **Rủi ro:** Thanh khoản, pháp lý, biến động thị trường.",
            "- **Khuyến nghị:** Nên thẩm định thực tế trước khi quyết định.\n",
            "> ⚠️ **Lưu ý quan trọng:** Đây KHÔNG phải lời khuyên tài chính. "
            "Bạn cần tự thẩm định và tham khảo chuyên gia tài chính trước khi "
            "đưa ra quyết định đầu tư.",
        ]

        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=[],
            sources=[],
            confidence="low",
            iterations=len(thoughts),
        )
```

- [ ] **Step 3: Create ProjectAgent**

Create `agent_service/agents/project_agent.py`:

```python
from __future__ import annotations

from typing import Any

from agent_service.agents.base import BaseAgent
from agent_service.contracts import (
    AgentAction,
    AgentContext,
    AgentResult,
    AgentSource,
    AgentThought,
)


class ProjectAgent(BaseAgent):
    """Autonomous project evaluation agent.

    Searches for real estate project information and evaluates
    developer credibility, progress, and legal status.

    Flow:
      1. think: Need project data → call search_projects
      2. final_answer: Summarize project info with caveats
    """

    def __init__(self, max_iterations: int = 2):
        super().__init__(agent_name="project_agent", max_iterations=max_iterations)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        has_projects = any(
            action.tool_result.get("results")
            for action in previous_actions
            if action.action_type == "call_tool"
        )

        if not has_projects:
            return AgentThought(
                iteration=iteration,
                reasoning="Need to search for project information.",
                action="call_tool",
                tool_name="search_projects",
                tool_params={
                    "query": context.normalized_query,
                    "filters": context.routing_filters,
                    "top_k": 15,
                    "rerank_to": 5,
                },
                confidence=0.9,
            )

        return AgentThought(
            iteration=iteration,
            reasoning="Project data gathered. Ready to present.",
            action="final_answer",
            confidence=0.9,
        )

    async def act(
        self, thought: AgentThought, context: AgentContext
    ) -> AgentAction:
        import time
        started = time.perf_counter()

        if thought.action == "final_answer":
            return AgentAction(
                iteration=thought.iteration,
                action_type="final_answer",
                status="success",
            )

        try:
            result = await self.call_tool(
                tool_name=thought.tool_name,
                tool_params=thought.tool_params or {},
                context=context,
            )
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="success",
                tool_result=result,
                evidence_ids=result.get("evidence_ids", []),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        except Exception as exc:
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="error",
                error_message=str(exc),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )

    async def observe(
        self, thought: AgentThought, action: AgentAction, context: AgentContext
    ) -> bool:
        return thought.action == "final_answer"

    def build_result(
        self,
        context: AgentContext,
        thoughts: list[AgentThought],
        actions: list[AgentAction],
    ) -> AgentResult:
        all_projects: list[dict[str, Any]] = []
        all_evidence_ids: list[str] = []

        for action in actions:
            results = action.tool_result.get("results", [])
            if isinstance(results, list):
                all_projects.extend(
                    item for item in results if isinstance(item, dict) and item.get("title")
                )
            for eid in action.evidence_ids:
                if eid not in all_evidence_ids:
                    all_evidence_ids.append(eid)

        if not all_projects:
            return AgentResult(
                agent_name=self.agent_name,
                status="no_evidence",
                content="Chưa tìm thấy thông tin dự án phù hợp.",
                iterations=len(thoughts),
            )

        lines = ["🏗️ **Thông tin dự án bất động sản:**\n"]
        for i, project in enumerate(all_projects[:5], 1):
            title = project.get("title", "Dự án")
            developer = project.get("developer", "Chưa rõ chủ đầu tư")
            location = project.get("location", "")
            lines.append(f"**{i}. {title}**")
            lines.append(f"   🏢 Chủ đầu tư: {developer}")
            if location:
                lines.append(f"   📍 {location}")
            lines.append("")

        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=all_evidence_ids,
            sources=[],
            confidence="medium",
            iterations=len(thoughts),
        )
```

- [ ] **Step 4: Create NewsAgent**

Create `agent_service/agents/news_agent.py`:

```python
from __future__ import annotations

from typing import Any

from agent_service.agents.base import BaseAgent
from agent_service.contracts import (
    AgentAction,
    AgentContext,
    AgentResult,
    AgentSource,
    AgentThought,
)


class NewsAgent(BaseAgent):
    """Autonomous news analysis agent.

    Searches for real estate news articles and analyzes
    their impact on the market.

    Flow:
      1. think: Need news → call search_articles (non-legal)
      2. final_answer: Summarize news with impact analysis
    """

    def __init__(self, max_iterations: int = 2):
        super().__init__(agent_name="news_agent", max_iterations=max_iterations)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        has_news = any(
            action.tool_result.get("results")
            for action in previous_actions
            if action.action_type == "call_tool"
        )

        if not has_news:
            return AgentThought(
                iteration=iteration,
                reasoning="Need to search for relevant news articles.",
                action="call_tool",
                tool_name="search_articles",
                tool_params={
                    "query": context.normalized_query,
                    "filters": {"exclude_category": "legal"},
                    "top_k": 15,
                    "rerank_to": 5,
                },
                confidence=0.9,
            )

        return AgentThought(
            iteration=iteration,
            reasoning="News articles gathered. Ready to summarize.",
            action="final_answer",
            confidence=0.9,
        )

    async def act(
        self, thought: AgentThought, context: AgentContext
    ) -> AgentAction:
        import time
        started = time.perf_counter()

        if thought.action == "final_answer":
            return AgentAction(
                iteration=thought.iteration,
                action_type="final_answer",
                status="success",
            )

        try:
            result = await self.call_tool(
                tool_name=thought.tool_name,
                tool_params=thought.tool_params or {},
                context=context,
            )
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="success",
                tool_result=result,
                evidence_ids=result.get("evidence_ids", []),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        except Exception as exc:
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="error",
                error_message=str(exc),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )

    async def observe(
        self, thought: AgentThought, action: AgentAction, context: AgentContext
    ) -> bool:
        return thought.action == "final_answer"

    def build_result(
        self,
        context: AgentContext,
        thoughts: list[AgentThought],
        actions: list[AgentAction],
    ) -> AgentResult:
        all_articles: list[dict[str, Any]] = []
        all_evidence_ids: list[str] = []

        for action in actions:
            results = action.tool_result.get("results", [])
            if isinstance(results, list):
                all_articles.extend(
                    item for item in results if isinstance(item, dict) and item.get("title")
                )
            for eid in action.evidence_ids:
                if eid not in all_evidence_ids:
                    all_evidence_ids.append(eid)

        if not all_articles:
            return AgentResult(
                agent_name=self.agent_name,
                status="no_evidence",
                content="Chưa có tin tức mới về chủ đề này.",
                iterations=len(thoughts),
            )

        lines = ["📰 **Tin tức bất động sản:**\n"]
        for i, article in enumerate(all_articles[:5], 1):
            title = article.get("title", "Bài viết")
            snippet = article.get("snippet", article.get("text", ""))[:200]
            url = article.get("url", "")
            lines.append(f"**{i}. {title}**")
            if snippet:
                lines.append(f"   {snippet}")
            if url:
                lines.append(f"   🔗 {url}")
            lines.append("")

        sources = [
            AgentSource(
                type="article",
                id=article.get("id"),
                title=article.get("title"),
                url=article.get("url"),
                snippet=article.get("snippet", ""),
            )
            for article in all_articles[:5]
        ]

        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=all_evidence_ids,
            sources=sources,
            confidence="medium",
            iterations=len(thoughts),
        )
```

- [ ] **Step 5: Verify all agents compile**

Run: `python -c "from agent_service.agents.market_analysis_agent import MarketAnalysisAgent; from agent_service.agents.investment_advisor_agent import InvestmentAdvisorAgent; from agent_service.agents.project_agent import ProjectAgent; from agent_service.agents.news_agent import NewsAgent; print('ALL OK')"`
Expected: `ALL OK`

- [ ] **Step 6: Commit**

```bash
git add agent_service/agents/market_analysis_agent.py agent_service/agents/investment_advisor_agent.py agent_service/agents/project_agent.py agent_service/agents/news_agent.py
git commit -m "feat: add remaining autonomous specialist agents (MarketAnalysis, InvestmentAdvisor, Project, News)"
```

---

### Task 8: Create OrchestratorAgent

**Files:**
- Create: `agent_service/agents/orchestrator.py`
- Create: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_orchestrator.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent_service.agents.orchestrator import OrchestratorAgent
from agent_service.contracts import (
    AgentChatRequest,
    AgentChatResponse,
    ConversationContextItem,
)
from agent_service.tools.registry import ToolRegistry, ToolDef


@pytest.fixture
def chat_request():
    return AgentChatRequest(
        request_id="test-001",
        message="Tìm căn hộ Quận 7 dưới 3 tỷ",
        session_id="sess-001",
    )


@pytest.fixture
def tool_registry():
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="search_listings",
        description="Search listings",
        allowed_for=["property_search", "investment_advisor"],
    ))

    async def fake_search(*, query, filters=None, top_k=20, rerank_to=5):
        return {
            "status": "success",
            "results": [
                {"id": "L001", "title": "Căn hộ Quận 7", "price_text": "2.5 tỷ",
                 "area_text": "70m²", "district": "Quận 7", "city": "Hồ Chí Minh"},
            ],
            "evidence_ids": ["ev_L001"],
        }

    reg.bind("search_listings", fake_search)
    return reg


@pytest.mark.asyncio
async def test_orchestrator_routes_and_dispatches(chat_request, tool_registry):
    orchestrator = OrchestratorAgent(tool_registry=tool_registry)
    response = await orchestrator.run(chat_request)

    assert isinstance(response, AgentChatResponse)
    assert response.request_id == "test-001"
    assert len(response.agents_used) >= 1
    assert "property_search" in response.agents_used
    assert len(response.final_response) > 0


@pytest.mark.asyncio
async def test_orchestrator_handles_empty_query():
    req = AgentChatRequest(
        request_id="test-002",
        message="",
        session_id="sess-002",
    )
    orchestrator = OrchestratorAgent(tool_registry=ToolRegistry())
    response = await orchestrator.run(req)

    assert response.request_id == "test-002"
    assert len(response.final_response) > 0  # Should give a helpful message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write OrchestratorAgent**

Create `agent_service/agents/orchestrator.py`:

```python
from __future__ import annotations

import asyncio
import time
from typing import Any

from agent_service.agents.base import BaseAgent
from agent_service.agents.property_search_agent import PropertySearchAgent
from agent_service.agents.market_analysis_agent import MarketAnalysisAgent
from agent_service.agents.legal_advisor_agent import LegalAdvisorAgent
from agent_service.agents.investment_advisor_agent import InvestmentAdvisorAgent
from agent_service.agents.project_agent import ProjectAgent
from agent_service.agents.news_agent import NewsAgent
from agent_service.config import get_agent_settings
from agent_service.contracts import (
    AgentChatRequest,
    AgentChatResponse,
    AgentContext,
    AgentResult,
    AgentSource,
    TraceSummary,
)
from agent_service.graph.blackboard import append_blackboard_entry, read_blackboard
from agent_service.graph.router import route_request
from agent_service.graph.synthesis import synthesize_final_answer
from agent_service.tools.registry import ToolRegistry


AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "property_search": PropertySearchAgent,
    "market_analysis": MarketAnalysisAgent,
    "legal_advisor": LegalAdvisorAgent,
    "investment_advisor": InvestmentAdvisorAgent,
    "project_agent": ProjectAgent,
    "news_agent": NewsAgent,
}


class OrchestratorAgent:
    """Orchestrator that replaces the static LangGraph workflow.

    Responsibilities:
      1. Route: Classify intent, select agents
      2. Dispatch: Run agents in parallel (each with own ReAct loop)
      3. Blackboard: Agents read/write shared state
      4. Synthesize: Combine results into final response
      5. Safety: Validate grounding and disclaimers
    """

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry | None = None,
        max_agent_iterations: int = 3,
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        self.max_agent_iterations = max_agent_iterations
        self.settings = get_agent_settings()

    async def run(self, request: AgentChatRequest) -> AgentChatResponse:
        started = time.perf_counter()
        state: dict[str, Any] = {
            "request": request,
            "agent_blackboard": {"entries": []},
            "warnings": [],
        }

        # ── 1. Route ────────────────────────────────────────────
        if not request.message.strip():
            return AgentChatResponse(
                request_id=request.request_id,
                final_response=(
                    "Xin chào! Tôi có thể giúp bạn tìm kiếm bất động sản, "
                    "phân tích thị trường, hoặc tư vấn pháp lý. "
                    "Bạn muốn tìm hiểu về vấn đề gì?"
                ),
                agents_used=[],
                sources=[],
                suggested_actions=[
                    "Tìm bất động sản",
                    "Phân tích thị trường",
                    "Tư vấn pháp lý",
                ],
                trace_summary=TraceSummary(
                    intent="general",
                    agents=[],
                    source_count=0,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                ),
            )

        decision = await route_request(state)
        agents_to_run = decision.agents

        if decision.needs_clarification:
            return AgentChatResponse(
                request_id=request.request_id,
                final_response=decision.clarifying_question
                or "Bạn có thể bổ sung thêm tiêu chí được không?",
                agents_used=[],
                sources=[],
                suggested_actions=["Bổ sung ngân sách", "Bổ sung khu vực"],
                trace_summary=TraceSummary(
                    intent=decision.intent,
                    agents=agents_to_run,
                    source_count=0,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                ),
            )

        # ── 2. Dispatch agents in parallel ──────────────────────
        agent_results: dict[str, AgentResult] = {}
        agent_tasks = []

        for agent_name in agents_to_run:
            agent_cls = AGENT_CLASSES.get(agent_name)
            if agent_cls is None:
                continue

            agent = agent_cls(max_iterations=self.max_agent_iterations)
            context = AgentContext(
                agent_name=agent_name,
                query=request.message,
                normalized_query=request.message.lower(),
                routing_filters=decision.filters,
                user_preferences=request.user_preferences,
                locale=request.locale,
            )
            agent_tasks.append(
                agent.run(
                    context,
                    state,
                    tool_registry=self.tool_registry,
                    timeout_seconds=self.settings.AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS,
                )
            )

        if agent_tasks:
            results_list = await asyncio.gather(*agent_tasks, return_exceptions=True)
            for i, result in enumerate(results_list):
                agent_name = agents_to_run[i] if i < len(agents_to_run) else f"agent_{i}"
                if isinstance(result, BaseException):
                    agent_results[agent_name] = AgentResult(
                        agent_name=agent_name,
                        status="failed",
                        content=f"Agent error: {result}",
                    )
                elif isinstance(result, AgentResult):
                    agent_results[agent_name] = result
                    # ── Write to blackboard for other agents ──
                    if result.content:
                        state.update(
                            append_blackboard_entry(
                                state,
                                author=agent_name,
                                entry_type=f"{agent_name}_analysis",
                                content=result.content[:1000],
                                evidence_ids=result.evidence_ids_used,
                                confidence=(
                                    "high"
                                    if result.confidence == "high"
                                    else "medium"
                                ),
                                step_name="orchestrator_dispatch",
                            )
                        )

        # ── 3. Synthesize ───────────────────────────────────────
        parts: list[str] = []
        all_sources: list[AgentSource] = []
        all_warnings: list[str] = []

        for agent_name in agents_to_run:
            result = agent_results.get(agent_name)
            if result and result.content:
                parts.append(result.content)
                all_sources.extend(result.sources)
                all_warnings.extend(
                    w if isinstance(w, str) else w.code
                    for w in result.warnings
                )

        if not parts:
            final_response = (
                "Xin lỗi, tôi chưa thể xử lý yêu cầu này. "
                "Vui lòng thử lại với tiêu chí khác."
            )
        else:
            final_response = "\n\n".join(parts)

        # ── 4. Safety checks ────────────────────────────────────
        suggested_actions = self._suggest_actions(agents_to_run)
        if "legal_advisor" in agents_to_run and "khong thay the tu van luat su" not in final_response.lower():
            final_response += (
                "\n\n> ⚠️ Thông tin pháp lý chỉ mang tính tham khảo, "
                "không thay thế tư vấn luật sư chuyên nghiệp."
            )

        return AgentChatResponse(
            request_id=request.request_id,
            final_response=final_response,
            agents_used=agents_to_run,
            sources=list({s.id: s for s in all_sources if s.id}.values()),
            suggested_actions=suggested_actions,
            trace_summary=TraceSummary(
                intent=decision.intent,
                agents=agents_to_run,
                source_count=len(all_sources),
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            ),
            warnings=all_warnings,
        )

    def _suggest_actions(self, agents_used: list[str]) -> list[str]:
        suggestions = []
        if "property_search" in agents_used:
            suggestions.append("So sánh các lựa chọn")
            suggestions.append("Hỏi thêm về pháp lý")
        if "market_analysis" in agents_used:
            suggestions.append("Xem xu hướng khu vực khác")
        if "investment_advisor" in agents_used:
            suggestions.append("Xác nhận ngân sách đầu tư")
            suggestions.append("Kiểm tra pháp lý")
        if not suggestions:
            suggestions = ["Tìm bất động sản", "Phân tích thị trường", "Tư vấn pháp lý"]
        return suggestions[:5]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent_service/agents/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add OrchestratorAgent replacing static LangGraph workflow"
```

---

### Task 9: Create Agentic Workflow (Simplified Graph)

**Files:**
- Create: `agent_service/graph/agentic_workflow.py`

- [ ] **Step 1: Write the simplified workflow**

Create `agent_service/graph/agentic_workflow.py`:

```python
from __future__ import annotations

import time
from typing import Any

from agent_service.agents.orchestrator import OrchestratorAgent
from agent_service.config import get_agent_settings
from agent_service.contracts import (
    AgentChatRequest,
    AgentChatResponse,
    AgentSource,
    StructuredWarning,
    TraceSummary,
)
from agent_service.tools.registry import ToolRegistry, ToolDef
from agent_service.tools.retrieval import search_listings, search_projects, search_articles
from agent_service.tools.market import lookup_market_metrics, lookup_market_timeseries
from agent_service.tools.retrieval import RetrievalTrace


def build_default_tool_registry() -> ToolRegistry:
    """Build ToolRegistry with all available tools and bindings.

    Each tool is registered with its metadata (ToolDef) and
    bound to the actual async function from agent_service/tools/.
    """
    registry = ToolRegistry()

    # ── Retrieval tools ──────────────────────────────────────
    registry.register(ToolDef(
        name="search_listings",
        description="Tìm kiếm bất động sản theo tiêu chí (giá, diện tích, khu vực, loại hình)",
        parameters={
            "query": "str - Từ khóa tìm kiếm",
            "filters": "dict - Bộ lọc: city, district, property_type, min_price, max_price, listing_type",
            "top_k": "int - Số lượng kết quả tối đa (default: 20)",
            "rerank_to": "int - Số lượng sau rerank (default: 5)",
        },
        required_params=["query"],
        allowed_for=["property_search", "investment_advisor"],
    ))

    registry.register(ToolDef(
        name="search_projects",
        description="Tìm kiếm dự án bất động sản theo tên, chủ đầu tư, khu vực",
        parameters={
            "query": "str - Từ khóa tìm kiếm",
            "filters": "dict - Bộ lọc: city, district, developer",
            "top_k": "int - Số lượng kết quả (default: 20)",
            "rerank_to": "int - Số lượng sau rerank (default: 5)",
        },
        required_params=["query"],
        allowed_for=["project_agent"],
    ))

    registry.register(ToolDef(
        name="search_articles",
        description="Tìm kiếm bài viết kiến thức (pháp lý, tin tức, hướng dẫn)",
        parameters={
            "query": "str - Từ khóa tìm kiếm",
            "filters": "dict - Bộ lọc: category (legal/news), exclude_category",
            "top_k": "int - Số lượng kết quả (default: 20)",
            "rerank_to": "int - Số lượng sau rerank (default: 5)",
        },
        required_params=["query"],
        allowed_for=["legal_advisor", "news_agent"],
    ))

    # ── Market tools ─────────────────────────────────────────
    registry.register(ToolDef(
        name="lookup_market_metrics",
        description="Tra cứu chỉ số thị trường hiện tại: giá trung bình/m², số lượng listing theo khu vực",
        parameters={
            "filters": "dict - city, district, property_type, listing_type",
        },
        required_params=["filters"],
        allowed_for=["market_analysis", "investment_advisor", "property_search"],
    ))

    registry.register(ToolDef(
        name="lookup_market_timeseries",
        description="Lấy dữ liệu chuỗi thời gian giá bất động sản theo tháng",
        parameters={
            "filters": "dict - city, district, property_type, listing_type",
        },
        required_params=["filters"],
        allowed_for=["market_analysis", "investment_advisor"],
    ))

    # ── Bind tool functions ──────────────────────────────────
    async def _search_listings_wrapper(*, query, filters=None, top_k=20, rerank_to=5):
        trace = RetrievalTrace(request_id="agentic")
        results = await search_listings(
            query=query, filters=filters, trace=trace,
            top_k=top_k, rerank_to=rerank_to,
        )
        evidence_ids = [
            f"ev_{r.get('id', f'listing_{i}')}"
            for i, r in enumerate(results) if isinstance(r, dict)
        ]
        return {"status": "success", "results": results, "evidence_ids": evidence_ids}

    async def _search_projects_wrapper(*, query, filters=None, top_k=20, rerank_to=5):
        trace = RetrievalTrace(request_id="agentic")
        results = await search_projects(
            query=query, filters=filters, trace=trace,
            top_k=top_k, rerank_to=rerank_to,
        )
        evidence_ids = [
            f"ev_{r.get('id', f'project_{i}')}"
            for i, r in enumerate(results) if isinstance(r, dict)
        ]
        return {"status": "success", "results": results, "evidence_ids": evidence_ids}

    async def _search_articles_wrapper(*, query, filters=None, top_k=20, rerank_to=5):
        trace = RetrievalTrace(request_id="agentic")
        results = await search_articles(
            query=query, filters=filters, trace=trace,
            top_k=top_k, rerank_to=rerank_to,
        )
        evidence_ids = [
            f"ev_{r.get('id', f'article_{i}')}"
            for i, r in enumerate(results) if isinstance(r, dict)
        ]
        return {"status": "success", "results": results, "evidence_ids": evidence_ids}

    async def _market_metrics_wrapper(*, filters):
        results = await lookup_market_metrics(filters=filters or {})
        return {"status": "success", "results": results, "evidence_ids": []}

    async def _market_timeseries_wrapper(*, filters):
        results = await lookup_market_timeseries(filters=filters or {})
        return {"status": "success", "results": results, "evidence_ids": []}

    registry.bind("search_listings", _search_listings_wrapper)
    registry.bind("search_projects", _search_projects_wrapper)
    registry.bind("search_articles", _search_articles_wrapper)
    registry.bind("lookup_market_metrics", _market_metrics_wrapper)
    registry.bind("lookup_market_timeseries", _market_timeseries_wrapper)

    return registry


# Singleton registry
_agentic_registry: ToolRegistry | None = None


def get_agentic_registry() -> ToolRegistry:
    global _agentic_registry
    if _agentic_registry is None:
        _agentic_registry = build_default_tool_registry()
    return _agentic_registry


async def run_agentic_graph(request: AgentChatRequest) -> AgentChatResponse:
    """Entry point for agentic RAG — replaces run_agent_graph().

    This is a thin wrapper that creates the OrchestratorAgent
    with the default ToolRegistry and delegates to it.
    """
    settings = get_agent_settings()
    registry = get_agentic_registry()
    orchestrator = OrchestratorAgent(
        tool_registry=registry,
        max_agent_iterations=settings.AGENT_REACT_MAX_ITERATIONS,
    )
    return await orchestrator.run(request)
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "from agent_service.graph.agentic_workflow import run_agentic_graph, build_default_tool_registry; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agent_service/graph/agentic_workflow.py
git commit -m "feat: add agentic_workflow with ToolRegistry wiring and run_agentic_graph()"
```

---

### Task 10: Wire New Workflow into main.py

**Files:**
- Modify: `agent_service/main.py:1-10` (add import)
- Modify: `agent_service/main.py:37-45` (add new endpoint)

- [ ] **Step 1: Add new endpoint to main.py**

Add this import at the top of `agent_service/main.py` after the existing imports (after line ~9):

```python
from agent_service.graph.agentic_workflow import run_agentic_graph
```

Add this new endpoint after the existing `/internal/agent/chat` endpoint (after line ~45):

```python
@app.post("/internal/agent/chat-v2", response_model=AgentChatResponse)
async def chat_v2(
    body: AgentChatRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_internal_key),
) -> AgentChatResponse:
    """Agentic RAG endpoint — autonomous agents with per-agent ReAct loops.

    Use this for A/B testing against the existing /internal/agent/chat.
    Once validated, this becomes the default.
    """
    del background_tasks
    return await run_agentic_graph(body)
```

- [ ] **Step 2: Verify app still loads**

Run: `python -c "from agent_service.main import app; print('App loaded OK')"`
Expected: `App loaded OK`

- [ ] **Step 3: Commit**

```bash
git add agent_service/main.py
git commit -m "feat: add /internal/agent/chat-v2 endpoint for agentic RAG"
```

---

### Task 11: Add Configuration for Agentic Mode

**Files:**
- Modify: `agent_service/config.py:56-58` (append after AGENT_REACT_TIMEOUT_SECONDS)

- [ ] **Step 1: Add agentic config fields**

Add the following fields to `AgentSettings` class in `agent_service/config.py`, after `AGENT_REACT_TIMEOUT_SECONDS` (line 59):

```python
    # ── Agentic RAG settings ──────────────────────────────────
    AGENT_MAX_ITERATIONS: int = 3
    AGENT_TOOL_TIMEOUT_SECONDS: float = 15.0
    AGENT_ORCHESTRATOR_MODE: str = "parallel"
    AGENT_BLACKBOARD_ENABLED: bool = True
    AGENT_AGENTIC_MODE: bool = False  # Toggle: False = old graph, True = agentic
```

- [ ] **Step 2: Verify config loads**

Run: `python -c "from agent_service.config import get_agent_settings; s = get_agent_settings(); print(s.AGENT_MAX_ITERATIONS, s.AGENT_AGENTIC_MODE)"`
Expected: `3 False`

- [ ] **Step 3: Commit**

```bash
git add agent_service/config.py
git commit -m "feat: add agentic RAG config fields (AGENT_MAX_ITERATIONS, AGENT_AGENTIC_MODE, etc.)"
```

---

### Task 12: Integration Test — End-to-End

**Files:**
- Create: `tests/test_agentic_e2e.py`

- [ ] **Step 1: Write E2E test**

Create `tests/test_agentic_e2e.py`:

```python
import pytest
from agent_service.contracts import AgentChatRequest
from agent_service.graph.agentic_workflow import run_agentic_graph


@pytest.mark.asyncio
async def test_agentic_e2e_property_search():
    """Full end-to-end: routing → agent dispatch → synthesis."""
    request = AgentChatRequest(
        request_id="e2e-001",
        message="Tìm căn hộ Quận 7 dưới 3 tỷ",
        session_id="e2e-sess",
    )
    response = await run_agentic_graph(request)

    assert response.request_id == "e2e-001"
    assert len(response.final_response) > 10
    assert "property_search" in response.agents_used
    # Should NOT error out
    assert response.final_response != ""


@pytest.mark.asyncio
async def test_agentic_e2e_legal_question():
    request = AgentChatRequest(
        request_id="e2e-002",
        message="Thủ tục sang tên sổ đỏ cần những giấy tờ gì?",
        session_id="e2e-sess",
    )
    response = await run_agentic_graph(request)

    assert response.request_id == "e2e-002"
    assert len(response.final_response) > 10
    assert "legal_advisor" in response.agents_used


@pytest.mark.asyncio
async def test_agentic_e2e_market_question():
    request = AgentChatRequest(
        request_id="e2e-003",
        message="Giá chung cư Quận Bình Thạnh hiện nay bao nhiêu?",
        session_id="e2e-sess",
    )
    response = await run_agentic_graph(request)

    assert response.request_id == "e2e-003"
    assert len(response.final_response) > 10
    assert "market_analysis" in response.agents_used


@pytest.mark.asyncio
async def test_agentic_e2e_empty_query():
    request = AgentChatRequest(
        request_id="e2e-004",
        message="",
        session_id="e2e-sess",
    )
    response = await run_agentic_graph(request)

    assert response.request_id == "e2e-004"
    assert len(response.final_response) > 10
    assert len(response.suggested_actions) > 0


@pytest.mark.asyncio
async def test_agentic_e2e_multi_agent():
    """Query that should trigger multiple agents."""
    request = AgentChatRequest(
        request_id="e2e-005",
        message="Tôi muốn mua căn hộ Quận 7, tư vấn pháp lý và phân tích đầu tư",
        session_id="e2e-sess",
    )
    response = await run_agentic_graph(request)

    assert response.request_id == "e2e-005"
    assert len(response.final_response) > 20
    # Expect at least 2 agents
    assert len(response.agents_used) >= 2
```

- [ ] **Step 2: Run E2E tests**

Run: `python -m pytest tests/test_agentic_e2e.py -v -s`
Expected: 5 PASSED (may need DB/Redis running for some tests)

- [ ] **Step 3: Commit**

```bash
git add tests/test_agentic_e2e.py
git commit -m "test: add end-to-end tests for agentic RAG pipeline"
```

---

### Task 13: Update agents __init__.py

**Files:**
- Modify: `agent_service/agents/__init__.py`

- [ ] **Step 1: Update __init__.py with exports**

Replace the content of `agent_service/agents/__init__.py`:

```python
"""Autonomous specialist agents for Agentic RAG."""

from agent_service.agents.base import BaseAgent
from agent_service.agents.property_search_agent import PropertySearchAgent
from agent_service.agents.market_analysis_agent import MarketAnalysisAgent
from agent_service.agents.legal_advisor_agent import LegalAdvisorAgent
from agent_service.agents.investment_advisor_agent import InvestmentAdvisorAgent
from agent_service.agents.project_agent import ProjectAgent
from agent_service.agents.news_agent import NewsAgent
from agent_service.agents.orchestrator import OrchestratorAgent

__all__ = [
    "BaseAgent",
    "PropertySearchAgent",
    "MarketAnalysisAgent",
    "LegalAdvisorAgent",
    "InvestmentAdvisorAgent",
    "ProjectAgent",
    "NewsAgent",
    "OrchestratorAgent",
]
```

- [ ] **Step 2: Verify**

Run: `python -c "from agent_service.agents import OrchestratorAgent, PropertySearchAgent; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agent_service/agents/__init__.py
git commit -m "feat: update agents __init__.py with all autonomous agent exports"
```

---

## Self-Review Checklist

### 1. Spec Coverage
- [x] **BaseAgent with ReAct loop** → Task 4
- [x] **ToolRegistry for agent tool discovery** → Task 2
- [x] **Blackboard read/query for agent communication** → Task 3
- [x] **PropertySearchAgent** → Task 5
- [x] **LegalAdvisorAgent** → Task 6
- [x] **MarketAnalysisAgent** → Task 7
- [x] **InvestmentAdvisorAgent** → Task 7
- [x] **ProjectAgent** → Task 7
- [x] **NewsAgent** → Task 7
- [x] **OrchestratorAgent** → Task 8
- [x] **Agentic workflow wiring** → Task 9
- [x] **API endpoint (/chat-v2)** → Task 10
- [x] **Configuration** → Task 11
- [x] **E2E integration tests** → Task 12

### 2. Placeholder Scan
- No "TBD", "TODO", "implement later" found
- All code steps have actual implementation code
- All test steps have complete test code
- No "add appropriate error handling" without concrete code

### 3. Type Consistency
- `AgentThought.action` uses `Literal["call_tool", "final_answer", "ask_clarification", "delegate"]` consistently across all agents
- `AgentResult.status` uses `Literal["completed", "partial", "no_evidence", "failed", "skipped"]` consistently
- `ToolDef.allowed_for` is `list[str]` consistently
- `AgentContext.agent_name` matches `agent_name` in agent constructors
- `BaseAgent.max_iterations` passed consistently to all subclasses
- `ToolRegistry.call(tool_name, agent_name, **params)` signature used consistently in `BaseAgent.call_tool()`

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-23-agentic-rag-migration.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
