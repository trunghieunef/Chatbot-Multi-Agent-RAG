# Agentic RAG Native Tool-Calling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the deterministic fake-agentic chat path with a real supervisor + specialist sub-agent graph that reasons via native Gemini function-calling and answers with grounded synthesis.

**Architecture:** A LangGraph `StateGraph` where a supervisor selects a subset of specialists, fans them out in parallel via `Send`, each specialist runs a native-function-calling ReAct loop over its allowed tools, and a grounded synthesizer produces Vietnamese prose citing only retrieved evidence. Listing cards render from `sources`; the LLM never invents listing facts.

**Tech Stack:** Python 3 async, FastAPI, LangGraph 1.2.1, `google-genai` 2.2.0 (native function-calling), `langgraph-checkpoint-sqlite` (AsyncSqliteSaver), pgvector hybrid search (reused), pytest + pytest-asyncio.

## Global Constraints

- Run all Python commands **from the repo root** so `agent_service.*` and `app.*` both import (`agent_service/tests/conftest.py` inserts ROOT + BACKEND into `sys.path`).
- Tests MUST run **offline**: never call real Gemini or a live DB. Inject a fake LLM client and monkeypatch tool/retrieval functions (mirror existing `agent_service/tests` patterns).
- Do **not** change the public contract: `AgentChatResponse` fields stay as defined in `agent_service/contracts.py`. Backend (`backend/app/services/agent_service/client.py`) and frontend are untouched this milestone.
- Chatbot-facing text (final responses, prompts, suggestions) in **Vietnamese**; code/comments/docstrings in **English**.
- Streaming is **out of scope**: keep `POST /internal/agent/chat` non-streaming. Do not delete `run_agentic_graph_stream` yet, but it may stay on the old behavior until the streaming milestone.
- Multi-turn source of truth = `request.conversation_context` (backend-built). SQLite checkpoint is for resume/observability only.
- Honor existing flags from `agent_service/config.py`: `AGENT_ROUTER_MODE` (`rule|llm|hybrid`), `AGENT_MAX_ITERATIONS`, `AGENT_SPECIALIST_LLM_ENABLED`, `AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS`, `AGENT_LLM_CONFIDENCE_THRESHOLD`, cost/budget guard, `AGENT_CHECKPOINT_ENABLED`, `AGENT_CHECKPOINT_PATH`, `AGENT_TOOL_RETRY_MAX`, `AGENT_TOOL_RETRY_BACKOFF_SECONDS`.
- `google-genai` is version 2.2.0 and `langgraph` is 1.2.1 (verified installed). Use `from google import genai` / `from google.genai import types`.

---

## Pre-flight: current state facts (read before starting)

- Live path today: `agent_service/main.py` → `agent_service/graph/agentic_workflow.py::run_agentic_graph` (deterministic `_agent_think`).
- Genuinely-agentic but **dead** code we will reuse: `agent_service/agents/*.py` (specialist `build_result` + `_role_description`), `agent_service/graph/synthesis.py::synthesize_final_answer` (grounding validation), `agent_service/graph/blackboard.py`, `agent_service/graph/committee.py`, `agent_service/graph/investment_model.py`.
- **13 test files currently fail to collect** because they import removed modules (`agent_service.graph.workflow`, `graph.nodes`, `graph.react_controller`, `graph.retrieval_planner`). They test a third, already-deleted architecture. Task 1 quarantines them so the suite is green for TDD.
- `agent_service/config.py::require_explicit_model_for_live_llm` raises if `GEMINI_API_KEY` set + live LLM enabled + `GEMINI_MODEL` not explicitly set. `GeminiClient.generate_text_with_usage` adds a redundant *soft* skip on the same condition. New FC method must not reproduce the soft skip.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `agent_service/tests/conftest.py` | Quarantine orphaned (dead-module) test files | Modify |
| `agent_service/llm/gemini.py` | Add `run_tool_loop` native function-calling helper | Modify |
| `agent_service/llm/function_schema.py` | Convert `ToolDef` → `types.FunctionDeclaration` | Create |
| `agent_service/agents/fc_runner.py` | Native-FC specialist runner + deterministic fallback | Create |
| `agent_service/graph/router.py` | Thread `conversation_context` into planner | Modify |
| `agent_service/graph/synthesis.py` | Extend `synthesize_final_answer` signature | Modify |
| `agent_service/graph/agentic_workflow.py` | Supervisor + Send dispatch + specialist + synth nodes | Rewrite |
| `agent_service/requirements.txt` | Add `langgraph-checkpoint-sqlite` | Modify |
| `agent_service/Dockerfile` | (no change unless pip install line pins) | Verify |
| `agent_service/tests/test_fc_*.py` etc. | New tests per task | Create |

---

## Task 1: Quarantine orphaned tests so the suite is green

**Files:**
- Modify: `agent_service/tests/conftest.py`

**Interfaces:**
- Produces: a collectable test suite (`pytest agent_service/tests` runs with 0 collection errors).

- [ ] **Step 1: Confirm the current breakage**

Run: `python -m pytest agent_service/tests --collect-only -q 2>&1 | tail -5`
Expected: `13 errors during collection` referencing `cannot import name 'nodes'/'workflow'/'react_controller'/'retrieval_planner'`.

- [ ] **Step 2: Add a collect-ignore list to conftest**

Append to `agent_service/tests/conftest.py`:

```python
# Test files that import a removed agent architecture
# (graph.workflow / graph.nodes / graph.react_controller / graph.retrieval_planner).
# Quarantined here so the suite collects; triage/delete in a later cleanup.
collect_ignore = [
    "test_agentic_e2e.py",
    "test_blackboard_specialists.py",
    "test_collaborative_investment_graph.py",
    "test_conversation_context.py",
    "test_graph_smoke.py",
    "test_investment_calculators.py",
    "test_investment_model_node.py",
    "test_investment_safety.py",
    "test_investment_trace.py",
    "test_memory_node.py",
    "test_react_loop.py",
    "test_retrieval_parallel.py",
    "test_specialists_parallel.py",
]
```

- [ ] **Step 3: Verify the suite now collects and passes**

Run: `python -m pytest agent_service/tests -q`
Expected: collection succeeds (no import errors); remaining tests pass.

- [ ] **Step 4: Commit**

```bash
git add agent_service/tests/conftest.py
git commit -m "test: quarantine orphaned tests importing removed agent modules"
```

---

## Task 2: Native function-calling helper in GeminiClient

**Files:**
- Modify: `agent_service/llm/gemini.py`
- Test: `agent_service/tests/test_gemini_tool_loop.py`

**Interfaces:**
- Consumes: existing `GeminiClient.__init__`, `_llm_semaphore`, `record_runtime_llm_cost`.
- Produces:
  ```python
  # collected tool call, normalized
  @dataclass(frozen=True)
  class ToolLoopStep:
      tool_name: str
      args: dict[str, Any]
      result: dict[str, Any]
  @dataclass(frozen=True)
  class ToolLoopResult:
      text: str
      steps: list[ToolLoopStep]
      iterations: int
      skipped_reason: str | None = None
  async def GeminiClient.run_tool_loop(
      self, *, system_prompt: str, user_message: str,
      function_declarations: list[Any],          # list[types.FunctionDeclaration]
      executor: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
      max_iterations: int, timeout_seconds: float,
  ) -> ToolLoopResult: ...
  ```

- [ ] **Step 1: Write the failing test**

Create `agent_service/tests/test_gemini_tool_loop.py`:

```python
from __future__ import annotations

import types as pytypes
import pytest

from agent_service.llm import gemini


class _FakeFunctionCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class _FakeResponse:
    def __init__(self, function_calls=None, text=""):
        self.function_calls = function_calls or []
        self.text = text
        self.usage_metadata = pytypes.SimpleNamespace(
            prompt_token_count=10, candidates_token_count=5
        )


class _FakeModels:
    def __init__(self, responses):
        self._responses = list(responses)

    def generate_content(self, **kwargs):
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses):
        self.models = _FakeModels(responses)


@pytest.mark.asyncio
async def test_run_tool_loop_executes_tool_then_returns_text(monkeypatch):
    # First model turn: ask for a tool. Second turn: final text.
    responses = [
        _FakeResponse(function_calls=[_FakeFunctionCall("search_listings", {"query": "q"})]),
        _FakeResponse(text="Đã tìm thấy 1 căn phù hợp."),
    ]
    monkeypatch.setattr(
        gemini.genai, "Client", lambda **kw: _FakeClient(responses), raising=False
    )

    calls = []

    async def executor(name, args):
        calls.append((name, args))
        return {"status": "success", "results": [{"id": 1, "title": "Căn A"}]}

    client = gemini.GeminiClient(api_key="k", model="gemini-2.5-flash")
    result = await client.run_tool_loop(
        system_prompt="role",
        user_message="Tìm căn hộ",
        function_declarations=[{"name": "search_listings"}],
        executor=executor,
        max_iterations=3,
        timeout_seconds=5.0,
    )

    assert result.text == "Đã tìm thấy 1 căn phù hợp."
    assert [s.tool_name for s in result.steps] == ["search_listings"]
    assert result.steps[0].result["results"][0]["id"] == 1
    assert calls == [("search_listings", {"query": "q"})]


@pytest.mark.asyncio
async def test_run_tool_loop_skips_without_api_key():
    client = gemini.GeminiClient(api_key="", model="gemini-2.5-flash")

    async def executor(name, args):
        raise AssertionError("executor must not run without api key")

    result = await client.run_tool_loop(
        system_prompt="role", user_message="x",
        function_declarations=[{"name": "t"}], executor=executor,
        max_iterations=2, timeout_seconds=5.0,
    )
    assert result.skipped_reason == "no_api_key"
    assert result.text == ""
    assert result.steps == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest agent_service/tests/test_gemini_tool_loop.py -q`
Expected: FAIL — `AttributeError: 'GeminiClient' object has no attribute 'run_tool_loop'` (and `gemini.genai` may not be imported at module scope yet).

- [ ] **Step 3: Implement `run_tool_loop`**

At the top of `agent_service/llm/gemini.py`, add the module-level import so tests can monkeypatch `gemini.genai.Client`:

```python
from google import genai
from google.genai import types
```

Add the dataclasses near `GeminiResult`:

```python
from collections.abc import Awaitable, Callable


@dataclass(frozen=True)
class ToolLoopStep:
    tool_name: str
    args: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True)
class ToolLoopResult:
    text: str
    steps: list["ToolLoopStep"]
    iterations: int
    skipped_reason: str | None = None
```

Add the method to `GeminiClient`:

```python
async def run_tool_loop(
    self,
    *,
    system_prompt: str,
    user_message: str,
    function_declarations: list[Any],
    executor: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
    max_iterations: int,
    timeout_seconds: float,
) -> ToolLoopResult:
    """Run a native function-calling ReAct loop.

    Each turn: ask the model; if it returns function calls, execute them via
    `executor`, append the results, and loop; otherwise return the final text.
    Does NOT gate on model_explicitly_configured (config validation already
    enforces an explicit model when live LLM is enabled).
    """
    if not self.api_key:
        return ToolLoopResult(text="", steps=[], iterations=0, skipped_reason="no_api_key")

    if self.settings.AGENT_LLM_COST_TRACKING_ENABLED:
        summary = get_runtime_cost_summary(self.settings)
        if not summary.get("tracking_available", True):
            return ToolLoopResult(text="", steps=[], iterations=0, skipped_reason="llm_cost_tracking_unavailable")
        if summary.get("budget_exceeded"):
            return ToolLoopResult(text="", steps=[], iterations=0, skipped_reason="llm_budget_exceeded")

    tools = [types.Tool(function_declarations=function_declarations)]
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=tools,
    )
    contents: list[Any] = [
        types.Content(role="user", parts=[types.Part(text=user_message)])
    ]
    steps: list[ToolLoopStep] = []
    http_options = {"timeout": int(timeout_seconds * 1000)}
    client = genai.Client(api_key=self.api_key, http_options=http_options)

    final_text = ""
    iteration = 0
    for iteration in range(1, max_iterations + 1):
        def _generate_sync(_contents=contents):
            return client.models.generate_content(
                model=self.model, contents=_contents, config=config
            )

        async with _llm_semaphore:
            response = await asyncio.wait_for(
                asyncio.to_thread(_generate_sync), timeout=timeout_seconds
            )

        usage = getattr(response, "usage_metadata", None)
        record_runtime_llm_cost(
            self.settings,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )

        function_calls = list(getattr(response, "function_calls", None) or [])
        if not function_calls:
            final_text = getattr(response, "text", "") or ""
            break

        # Record the model's function-call turn.
        contents.append(
            types.Content(
                role="model",
                parts=[
                    types.Part(function_call=types.FunctionCall(name=fc.name, args=dict(fc.args or {})))
                    for fc in function_calls
                ],
            )
        )
        response_parts = []
        for fc in function_calls:
            args = dict(fc.args or {})
            try:
                tool_result = await executor(fc.name, args)
            except Exception as exc:  # degrade, do not crash the loop
                tool_result = {"status": "error", "error": str(exc)[:300]}
            steps.append(ToolLoopStep(tool_name=fc.name, args=args, result=tool_result))
            response_parts.append(
                types.Part.from_function_response(name=fc.name, response={"result": tool_result})
            )
        contents.append(types.Content(role="user", parts=response_parts))

    return ToolLoopResult(text=final_text, steps=steps, iterations=iteration)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest agent_service/tests/test_gemini_tool_loop.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Verify the real SDK shape (manual, no network)**

Run: `python -c "from google.genai import types; print(hasattr(types.Part, 'from_function_response'), hasattr(types, 'FunctionCall'))"`
Expected: `True True`. If `from_function_response` is absent in this SDK build, replace with `types.Part(function_response=types.FunctionResponse(name=fc.name, response={'result': tool_result}))` and re-run Step 4.

- [ ] **Step 6: Commit**

```bash
git add agent_service/llm/gemini.py agent_service/tests/test_gemini_tool_loop.py
git commit -m "feat: add native function-calling tool loop to GeminiClient"
```

---

## Task 2b: Drop the redundant soft model-skip (footgun fix)

**Files:**
- Modify: `agent_service/llm/gemini.py:100-101` (the `model_explicitly_configured` early return inside `generate_text_with_usage`)
- Test: `agent_service/tests/test_gemini_tool_loop.py` (add one case)

**Interfaces:**
- Consumes: Task 2 `run_tool_loop`.
- Produces: a valid API key is sufficient to run the LLM; no silent skip when `GEMINI_MODEL` is a class default (config already validates this hard).

- [ ] **Step 1: Write the failing test**

Add to `agent_service/tests/test_gemini_tool_loop.py`:

```python
@pytest.mark.asyncio
async def test_generate_text_runs_with_api_key_even_if_model_is_default(monkeypatch):
    responses = [_FakeResponse(text="ok")]
    monkeypatch.setattr(gemini.genai, "Client", lambda **kw: _FakeClient(responses), raising=False)
    # model passed positionally => model_explicitly_configured True historically,
    # but we assert behavior holds when only api_key is provided.
    client = gemini.GeminiClient(api_key="k", model="gemini-2.5-flash")
    monkeypatch.setattr(client, "model_explicitly_configured", False, raising=False)
    out = await client.generate_text("hi")
    assert out == "ok"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest agent_service/tests/test_gemini_tool_loop.py::test_generate_text_runs_with_api_key_even_if_model_is_default -q`
Expected: FAIL — returns `""` because of the `if not self.model_explicitly_configured:` early return.

- [ ] **Step 3: Remove the soft skip**

In `agent_service/llm/gemini.py`, delete these two lines from `generate_text_with_usage`:

```python
        if not self.model_explicitly_configured:
            return GeminiResult(text="", skipped_reason="gemini_model_not_configured")
```

- [ ] **Step 4: Run the full gemini test file**

Run: `python -m pytest agent_service/tests/test_gemini_tool_loop.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add agent_service/llm/gemini.py agent_service/tests/test_gemini_tool_loop.py
git commit -m "fix: do not silently skip LLM when GEMINI_MODEL is a default"
```

---

## Task 3: ToolDef → FunctionDeclaration adapter

**Files:**
- Create: `agent_service/llm/function_schema.py`
- Test: `agent_service/tests/test_function_schema.py`

**Interfaces:**
- Consumes: `agent_service.contracts.ToolDef`.
- Produces:
  ```python
  def tooldef_to_function_declaration(tool_def: ToolDef) -> Any  # types.FunctionDeclaration
  def function_declarations_for(tool_defs: list[ToolDef]) -> list[Any]
  ```

- [ ] **Step 1: Write the failing test**

Create `agent_service/tests/test_function_schema.py`:

```python
from __future__ import annotations

from agent_service.contracts import ToolDef
from agent_service.llm.function_schema import (
    function_declarations_for,
    tooldef_to_function_declaration,
)


def test_maps_params_and_required():
    td = ToolDef(
        name="search_listings",
        description="Tìm BĐS",
        parameters={"query": "str", "filters": "dict", "top_k": "int"},
        required_params=["query"],
        allowed_for=["property_search"],
    )
    fd = tooldef_to_function_declaration(td)
    assert fd.name == "search_listings"
    assert fd.description == "Tìm BĐS"
    props = fd.parameters.properties
    assert set(props.keys()) == {"query", "filters", "top_k"}
    assert str(props["query"].type).upper().endswith("STRING")
    assert str(props["top_k"].type).upper().endswith("INTEGER")
    assert fd.parameters.required == ["query"]


def test_function_declarations_for_list():
    tds = [
        ToolDef(name="a", parameters={"x": "str"}),
        ToolDef(name="b", parameters={"y": "int"}),
    ]
    decls = function_declarations_for(tds)
    assert [d.name for d in decls] == ["a", "b"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest agent_service/tests/test_function_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: agent_service.llm.function_schema`.

- [ ] **Step 3: Implement the adapter**

Create `agent_service/llm/function_schema.py`:

```python
from __future__ import annotations

from typing import Any

from google.genai import types

from agent_service.contracts import ToolDef


_TYPE_MAP = {
    "str": types.Type.STRING,
    "string": types.Type.STRING,
    "int": types.Type.INTEGER,
    "integer": types.Type.INTEGER,
    "float": types.Type.NUMBER,
    "number": types.Type.NUMBER,
    "bool": types.Type.BOOLEAN,
    "boolean": types.Type.BOOLEAN,
    "dict": types.Type.OBJECT,
    "object": types.Type.OBJECT,
    "list": types.Type.ARRAY,
    "array": types.Type.ARRAY,
}


def _schema_for(py_type: str) -> types.Schema:
    gem_type = _TYPE_MAP.get(str(py_type).lower(), types.Type.STRING)
    if gem_type == types.Type.OBJECT:
        # Gemini requires OBJECT schemas to be open or have properties; keep open.
        return types.Schema(type=gem_type)
    if gem_type == types.Type.ARRAY:
        return types.Schema(type=gem_type, items=types.Schema(type=types.Type.STRING))
    return types.Schema(type=gem_type)


def tooldef_to_function_declaration(tool_def: ToolDef) -> types.FunctionDeclaration:
    properties = {
        name: _schema_for(py_type)
        for name, py_type in (tool_def.parameters or {}).items()
    }
    parameters = types.Schema(
        type=types.Type.OBJECT,
        properties=properties,
        required=list(tool_def.required_params or []),
    )
    return types.FunctionDeclaration(
        name=tool_def.name,
        description=tool_def.description or "",
        parameters=parameters,
    )


def function_declarations_for(
    tool_defs: list[ToolDef],
) -> list[types.FunctionDeclaration]:
    return [tooldef_to_function_declaration(td) for td in tool_defs]
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest agent_service/tests/test_function_schema.py -q`
Expected: PASS (2 passed). If `types.Type.STRING` enum repr differs, adjust the assertion in Step 1 to `props["query"].type == types.Type.STRING`.

- [ ] **Step 5: Commit**

```bash
git add agent_service/llm/function_schema.py agent_service/tests/test_function_schema.py
git commit -m "feat: add ToolDef to Gemini FunctionDeclaration adapter"
```

---

## Task 4: Native-FC specialist runner with deterministic fallback

**Files:**
- Create: `agent_service/agents/fc_runner.py`
- Test: `agent_service/tests/test_fc_runner.py`

**Interfaces:**
- Consumes: `ToolLoopResult`/`run_tool_loop` (Task 2), `function_declarations_for` (Task 3), `ToolRegistry.list_for_agent`/`.call`, `agent_service.agents.AGENT_CLASSES` (via orchestrator import) or per-name class map, `BaseAgent._role_description`, specialist `build_result`, `AgentContext`, `AgentResult`, `AgentAction`.
- Produces:
  ```python
  AGENT_CLASSES: dict[str, type[BaseAgent]]   # reused from agents.orchestrator
  async def run_specialist(
      *, agent_name: str, context: AgentContext, registry: ToolRegistry,
      llm_client: Any | None, settings: AgentSettings,
  ) -> AgentResult: ...
  ```
  `run_specialist` returns an `AgentResult` whose `sources` come from the specialist `build_result` and whose `content` is the LLM analysis text when available (else the template content). `evidence_ids_used` aggregates evidence from tool results.

- [ ] **Step 1: Write the failing test**

Create `agent_service/tests/test_fc_runner.py`:

```python
from __future__ import annotations

import pytest

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentContext, ToolDef
from agent_service.llm.gemini import ToolLoopResult, ToolLoopStep
from agent_service.tools.registry import ToolRegistry
from agent_service.agents import fc_runner


def _registry_with_listings(results):
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="search_listings", description="x",
        parameters={"query": "str", "filters": "dict"},
        required_params=["query"], allowed_for=["property_search"],
    ))

    async def _search(**kwargs):
        return {"status": "success", "results": results,
                "evidence_ids": [f"ev_{r['id']}" for r in results]}

    reg.bind("search_listings", _search)
    return reg


class _FakeLLM:
    def __init__(self, text):
        self._text = text

    async def run_tool_loop(self, *, executor, **kwargs):
        # Simulate the model calling the tool once, then answering.
        result = await executor("search_listings", {"query": "căn hộ"})
        return ToolLoopResult(
            text=self._text,
            steps=[ToolLoopStep("search_listings", {"query": "căn hộ"}, result)],
            iterations=2,
        )


@pytest.mark.asyncio
async def test_run_specialist_uses_llm_text_and_build_result_sources():
    listings = [{"id": 1, "title": "Căn A", "price_text": "2 tỷ",
                 "area_text": "60 m²", "district": "Quận 7", "city": "HCM"}]
    reg = _registry_with_listings(listings)
    ctx = AgentContext(agent_name="property_search", query="Tìm căn hộ Quận 7",
                       normalized_query="tim can ho quan 7", routing_filters={"city": "HCM"})
    result = await fc_runner.run_specialist(
        agent_name="property_search", context=ctx, registry=reg,
        llm_client=_FakeLLM("Tôi gợi ý căn A vì gần trung tâm."),
        settings=get_agent_settings(),
    )
    assert result.agent_name == "property_search"
    assert result.status == "completed"
    assert "căn A" in result.content.lower()           # LLM analysis text
    assert any(s.id == 1 for s in result.sources)       # cards from build_result
    assert "ev_1" in result.evidence_ids_used


@pytest.mark.asyncio
async def test_run_specialist_falls_back_to_deterministic_without_llm():
    listings = [{"id": 2, "title": "Căn B", "price_text": "3 tỷ",
                 "area_text": "70 m²", "district": "Quận 1", "city": "HCM"}]
    reg = _registry_with_listings(listings)
    ctx = AgentContext(agent_name="property_search", query="Tìm căn hộ",
                       normalized_query="tim can ho", routing_filters={})
    result = await fc_runner.run_specialist(
        agent_name="property_search", context=ctx, registry=reg,
        llm_client=None, settings=get_agent_settings(),
    )
    assert result.status == "completed"
    assert any(s.id == 2 for s in result.sources)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest agent_service/tests/test_fc_runner.py -q`
Expected: FAIL — `ModuleNotFoundError: agent_service.agents.fc_runner`.

- [ ] **Step 3: Implement the runner**

Create `agent_service/agents/fc_runner.py`:

```python
from __future__ import annotations

import logging
from typing import Any

from agent_service.agents.orchestrator import AGENT_CLASSES
from agent_service.agents.base import BaseAgent
from agent_service.config import AgentSettings
from agent_service.contracts import AgentAction, AgentContext, AgentResult
from agent_service.llm.function_schema import function_declarations_for
from agent_service.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _deterministic_actions_from_steps(steps: list[Any]) -> list[AgentAction]:
    """Wrap tool-loop steps as AgentActions so build_result can format them."""
    actions: list[AgentAction] = []
    for i, step in enumerate(steps):
        result = step.result if isinstance(step.result, dict) else {}
        evidence = result.get("evidence_ids", [])
        actions.append(AgentAction(
            iteration=i,
            action_type="call_tool",
            status="success" if result.get("status") == "success" else "error",
            tool_result=result,
            evidence_ids=evidence if isinstance(evidence, list) else [],
        ))
    return actions


async def _run_deterministic(agent: BaseAgent, context: AgentContext,
                             registry: ToolRegistry) -> AgentResult:
    """Fallback: run the agent's existing deterministic ReAct loop."""
    return await agent.run(
        context, state={"agent_blackboard": {"entries": []}},
        tool_registry=registry, llm_client=None,
        timeout_seconds=30.0,
    )


async def run_specialist(
    *,
    agent_name: str,
    context: AgentContext,
    registry: ToolRegistry,
    llm_client: Any | None,
    settings: AgentSettings,
) -> AgentResult:
    agent_cls = AGENT_CLASSES.get(agent_name)
    if agent_cls is None:
        return AgentResult(agent_name=agent_name, status="failed",
                           content=f"Unknown agent: {agent_name}")
    agent = agent_cls(max_iterations=settings.AGENT_MAX_ITERATIONS, use_llm=bool(llm_client))

    use_llm = bool(llm_client) and settings.AGENT_SPECIALIST_LLM_ENABLED
    if not use_llm:
        return await _run_deterministic(agent, context, registry)

    tool_defs = registry.list_for_agent(agent_name)
    declarations = function_declarations_for(tool_defs)

    async def executor(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        return await registry.call(tool_name=tool_name, agent_name=agent_name, **args)

    system_prompt = BaseAgent._role_description(agent_name)
    user_message = (
        f"Truy vấn người dùng: {context.query}\n"
        f"Bộ lọc: {context.routing_filters}\n"
        "Hãy dùng công cụ để lấy dữ liệu rồi đưa ra phân tích ngắn gọn bằng tiếng Việt. "
        "KHÔNG bịa thông tin không có trong kết quả công cụ."
    )

    try:
        loop = await llm_client.run_tool_loop(
            system_prompt=system_prompt,
            user_message=user_message,
            function_declarations=declarations,
            executor=executor,
            max_iterations=settings.AGENT_MAX_ITERATIONS,
            timeout_seconds=settings.AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("[%s] FC loop failed (%s); deterministic fallback", agent_name, exc)
        return await _run_deterministic(agent, context, registry)

    if loop.skipped_reason or not loop.steps:
        # No tool evidence gathered → use deterministic path to guarantee retrieval.
        return await _run_deterministic(agent, context, registry)

    actions = _deterministic_actions_from_steps(loop.steps)
    base_result = agent.build_result(context, thoughts=[], actions=actions)

    # Prefer LLM analysis text for content; keep structured sources/evidence.
    content = loop.text.strip() or base_result.content
    return base_result.model_copy(update={"content": content, "iterations": loop.iterations})
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest agent_service/tests/test_fc_runner.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the whole suite (no regressions)**

Run: `python -m pytest agent_service/tests -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent_service/agents/fc_runner.py agent_service/tests/test_fc_runner.py
git commit -m "feat: native function-calling specialist runner with deterministic fallback"
```

---

## Task 5: Thread conversation_context into the planner

**Files:**
- Modify: `agent_service/graph/router.py` (`_router_prompt`, `route_with_llm`)
- Test: `agent_service/tests/test_planner_context.py`

**Interfaces:**
- Consumes: existing `route_request(state, client=None)`, `RouterDecision`.
- Produces: `route_request` reads `state["conversation_context"]` (list of `{role, content}` dicts) and passes the last 3 turns into the LLM planner prompt. Rule mode unchanged.

- [ ] **Step 1: Write the failing test**

Create `agent_service/tests/test_planner_context.py`:

```python
from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph import router as router_mod
from agent_service.graph.router import RouterDecision, route_request


class _CapturingClient:
    def __init__(self):
        self.last_prompt = None

    async def generate_json(self, prompt, *, timeout_seconds=None):
        self.last_prompt = prompt
        return {"intent": "property_search", "agents": ["property_search"],
                "confidence": 0.9, "filters": {"district": "Quận 7"},
                "reason": "follow-up about district"}


@pytest.mark.asyncio
async def test_planner_prompt_includes_conversation_context(monkeypatch):
    monkeypatch.setenv("AGENT_ROUTER_MODE", "llm")
    from agent_service.config import get_agent_settings
    get_agent_settings.cache_clear()

    client = _CapturingClient()
    state = {
        "request": AgentChatRequest(
            request_id="r1", session_id="s1", message="thế còn quận 7?",
        ),
        "conversation_context": [
            {"role": "user", "content": "tìm căn hộ 2 phòng ngủ ở Hà Nội"},
            {"role": "assistant", "content": "Đây là vài lựa chọn ở Hà Nội..."},
        ],
    }
    decision = await route_request(state, client=client)
    get_agent_settings.cache_clear()

    assert isinstance(decision, RouterDecision)
    assert "quận 7" in client.last_prompt.lower()
    assert "phòng ngủ" in client.last_prompt.lower()  # prior turn is in the prompt
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest agent_service/tests/test_planner_context.py -q`
Expected: FAIL — prior-turn text "phòng ngủ" is not in the prompt (router currently reads `state.get("compact_context")`, which the graph never sets).

- [ ] **Step 3: Make the planner read conversation_context**

In `agent_service/graph/router.py`, change `route_with_llm` to source context from `conversation_context` (falling back to `compact_context`):

Replace:
```python
        payload = await client.generate_json(
            _router_prompt(request.message, state.get("compact_context", [])),
            timeout_seconds=settings.AGENT_LLM_ROUTER_TIMEOUT_SECONDS,
        )
```
with:
```python
        context = state.get("conversation_context") or state.get("compact_context", [])
        payload = await client.generate_json(
            _router_prompt(request.message, context),
            timeout_seconds=settings.AGENT_LLM_ROUTER_TIMEOUT_SECONDS,
        )
```

`_router_prompt` already renders `context[-3:]` into the prompt, so no change there.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest agent_service/tests/test_planner_context.py -q`
Expected: PASS.

- [ ] **Step 5: Run the suite**

Run: `python -m pytest agent_service/tests -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent_service/graph/router.py agent_service/tests/test_planner_context.py
git commit -m "feat: pass conversation_context into the LLM planner"
```

---

## Task 6: Extend grounded synthesis signature

**Files:**
- Modify: `agent_service/graph/synthesis.py` (`synthesize_final_answer`)
- Test: `agent_service/tests/test_synthesis_signature.py`

**Interfaces:**
- Consumes: existing `synthesize_final_answer`, `SynthesisResult`, grounding helpers.
- Produces: a backward-compatible signature that also accepts `supervisor_plan` and `evidence_by_id`:
  ```python
  async def synthesize_final_answer(
      *, query, conversation_context, agent_results, deterministic_response,
      default_actions, generate_json, timeout_seconds, allowed_evidence_ids=None,
      supervisor_plan: dict | None = None, evidence_by_id: dict | None = None,
  ) -> SynthesisResult: ...
  ```
  The new params are folded into the synthesis prompt; grounding behavior unchanged.

- [ ] **Step 1: Write the failing test**

Create `agent_service/tests/test_synthesis_signature.py`:

```python
from __future__ import annotations

import pytest

from agent_service.graph.synthesis import synthesize_final_answer


@pytest.mark.asyncio
async def test_synthesis_accepts_plan_and_evidence_map_and_rejects_fabricated_ids():
    captured = {}

    async def fake_generate_json(prompt, *, timeout_seconds=None):
        captured["prompt"] = prompt
        # Model fabricates an evidence id not in the allowed set.
        return {
            "final_response": "Giá khu vực là 50 tr/m².",
            "suggested_actions": ["So sánh thêm"],
            "claims": [{"text": "Giá 50 tr/m²", "evidence_ids": ["ev_999"]}],
            "evidence_ids_used": ["ev_999"],
        }

    result = await synthesize_final_answer(
        query="giá quận 7?",
        conversation_context=[],
        agent_results={"market_analysis": {"status": "completed", "content": "x",
                                           "evidence_ids_used": ["ev_1"]}},
        deterministic_response="Phản hồi dự phòng.",
        default_actions=["Tìm BĐS"],
        generate_json=fake_generate_json,
        timeout_seconds=5.0,
        allowed_evidence_ids={"ev_1"},
        supervisor_plan={"selected_agents": ["market_analysis"], "intent": "market_analysis"},
        evidence_by_id={"ev_1": {"metric": "avg_price_per_m2", "value": 48}},
    )
    assert result.used_llm is False                      # fabricated id rejected
    assert result.final_response == "Phản hồi dự phòng."
    assert "market_analysis" in captured["prompt"]       # plan reached the prompt
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest agent_service/tests/test_synthesis_signature.py -q`
Expected: FAIL — `TypeError: synthesize_final_answer() got an unexpected keyword argument 'supervisor_plan'`.

- [ ] **Step 3: Extend the signature and prompt**

In `agent_service/graph/synthesis.py`:

Change `build_synthesis_prompt` to accept and render the plan:
```python
def build_synthesis_prompt(
    *,
    query: str,
    conversation_context: list[dict[str, Any]],
    agent_results: dict[str, dict[str, Any]],
    supervisor_plan: dict[str, Any] | None = None,
) -> str:
```
Add, just before the final `return "\n".join([...])`, an extra line inside the list:
```python
            f"Supervisor plan: {json.dumps(supervisor_plan or {}, ensure_ascii=True, default=str)}",
```

Change `synthesize_final_answer` signature to add the two params and pass the plan through:
```python
async def synthesize_final_answer(
    *,
    query: str,
    conversation_context: list[dict[str, Any]],
    agent_results: dict[str, dict[str, Any]],
    deterministic_response: str,
    default_actions: list[str],
    generate_json: GenerateJson | None,
    timeout_seconds: float,
    allowed_evidence_ids: set[str] | None = None,
    supervisor_plan: dict[str, Any] | None = None,
    evidence_by_id: dict[str, Any] | None = None,
) -> SynthesisResult:
```
Inside, update the `generate_json(...)` call to pass `supervisor_plan`:
```python
        payload = await generate_json(
            build_synthesis_prompt(
                query=query,
                conversation_context=conversation_context,
                agent_results=agent_results,
                supervisor_plan=supervisor_plan,
            ),
            timeout_seconds=timeout_seconds,
        )
```
`evidence_by_id` is accepted for forward-compatibility (logging/future grounding); no behavior change required this task.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest agent_service/tests/test_synthesis_signature.py -q`
Expected: PASS.

- [ ] **Step 5: Run existing synthesis tests (no regression)**

Run: `python -m pytest agent_service/tests/test_synthesis.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent_service/graph/synthesis.py agent_service/tests/test_synthesis_signature.py
git commit -m "feat: accept supervisor_plan and evidence_by_id in grounded synthesis"
```

---

## Task 7: New supervisor + specialist + synthesize graph

**Files:**
- Rewrite: `agent_service/graph/agentic_workflow.py` (replace nodes; keep `build_default_tool_registry`, `get_agentic_registry`, `_attach_listing_images`)
- Modify: `agent_service/requirements.txt` (add `langgraph-checkpoint-sqlite>=2.0.0`)
- Test: `agent_service/tests/test_supervisor_graph.py`

**Interfaces:**
- Consumes: `run_specialist` (Task 4), `route_request` (Task 5), `synthesize_final_answer` (Task 6), `get_agentic_registry`, `GeminiClient`.
- Produces: `run_agentic_graph(request) -> AgentChatResponse` with **real** agentic behavior; supervisor selects a subset of agents; parallel dispatch via `Send`; reads its result from the `ainvoke` return value (not `aget_state`).

- [ ] **Step 1: Write the failing test**

Create `agent_service/tests/test_supervisor_graph.py`:

```python
from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest, AgentResult
from agent_service.graph.router import RouterDecision
from agent_service.graph import agentic_workflow as wf


@pytest.mark.asyncio
async def test_only_selected_agents_run_and_response_is_built(monkeypatch):
    # Supervisor selects exactly property_search + market_analysis.
    async def fake_route_request(state, client=None):
        return RouterDecision(intent="mixed",
                              agents=["property_search", "market_analysis"],
                              confidence=0.9, filters={"city": "HCM"})

    ran = []

    async def fake_run_specialist(*, agent_name, context, registry, llm_client, settings):
        ran.append(agent_name)
        return AgentResult(agent_name=agent_name, status="completed",
                           content=f"{agent_name} ok", evidence_ids_used=[f"ev_{agent_name}"])

    monkeypatch.setattr(wf, "route_request", fake_route_request)
    monkeypatch.setattr(wf, "run_specialist", fake_run_specialist)
    # Force deterministic synth (no LLM) for a stable assertion.
    monkeypatch.setattr(wf, "_make_llm_client", lambda settings: None)

    resp = await wf.run_agentic_graph(AgentChatRequest(
        request_id="r1", session_id="s1", message="So sánh giá căn hộ Quận 7"))

    assert sorted(ran) == ["market_analysis", "property_search"]
    assert "legal_advisor" not in ran        # NOT a fan-out of all 6
    assert resp.agents_used == ["property_search", "market_analysis"]
    assert "property_search ok" in resp.final_response
    assert "market_analysis ok" in resp.final_response


@pytest.mark.asyncio
async def test_clarification_short_circuits_specialists(monkeypatch):
    async def fake_route_request(state, client=None):
        return RouterDecision(intent="property_search", agents=["property_search"],
                              needs_clarification=True,
                              clarifying_question="Bạn muốn mua hay thuê?")

    async def fail_specialist(**kwargs):
        raise AssertionError("specialists must not run on clarification")

    monkeypatch.setattr(wf, "route_request", fake_route_request)
    monkeypatch.setattr(wf, "run_specialist", fail_specialist)
    monkeypatch.setattr(wf, "_make_llm_client", lambda settings: None)

    resp = await wf.run_agentic_graph(AgentChatRequest(
        request_id="r2", session_id="s1", message="Tìm căn hộ Quận 7"))
    assert resp.final_response == "Bạn muốn mua hay thuê?"
    assert resp.agents_used == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest agent_service/tests/test_supervisor_graph.py -q`
Expected: FAIL — `AttributeError` (`_make_llm_client`/new wiring not present; old deterministic `_node_dispatch_agents` still active).

- [ ] **Step 3: Rewrite the graph nodes**

In `agent_service/graph/agentic_workflow.py`, **keep** the imports plus `build_default_tool_registry`, `_attach_listing_images`, `get_agentic_registry`, `with_retry`. **Replace** everything from `_agent_think` through `run_agentic_graph` (keep `run_agentic_graph_stream` as-is for now) with:

```python
from operator import or_ as _dict_or
from typing import Annotated

from langgraph.constants import Send

from agent_service.agents.fc_runner import run_specialist
from agent_service.graph.synthesis import synthesize_final_answer
from agent_service.llm.gemini import GeminiClient


def _make_llm_client(settings) -> GeminiClient | None:
    if not settings.GEMINI_API_KEY:
        return None
    return GeminiClient()


def _conversation_context(request: AgentChatRequest) -> list[dict[str, str]]:
    return [
        {"role": item.role, "content": item.content}
        for item in request.conversation_context
    ]


async def _node_supervisor(state: dict[str, Any]) -> dict[str, Any]:
    request = state["request"]
    if not request.message.strip():
        return {"supervisor_plan": {"selected_agents": [], "needs_clarification": False,
                                    "intent": "general", "filters": {}},
                "agents_used": []}
    decision = await route_request({
        "request": request,
        "conversation_context": state.get("conversation_context", []),
        "normalized_query": request.message.lower(),
    })
    plan = decision.model_dump(mode="python")
    plan["selected_agents"] = decision.agents
    return {
        "supervisor_plan": plan,
        "routing_filters": decision.filters,
        "agents_used": decision.agents if not decision.needs_clarification else [],
    }


def _dispatch(state: dict[str, Any]):
    plan = state.get("supervisor_plan") or {}
    if plan.get("needs_clarification") or not plan.get("selected_agents"):
        return "synthesize"
    return [Send("specialist", {"agent_name": name, **state})
            for name in plan["selected_agents"]]


async def _node_specialist(state: dict[str, Any]) -> dict[str, Any]:
    agent_name = state["agent_name"]
    request = state["request"]
    settings = get_agent_settings()
    registry = get_agentic_registry()
    context = AgentContext(
        agent_name=agent_name, query=request.message,
        normalized_query=request.message.lower(),
        routing_filters=state.get("routing_filters", {}),
        conversation_context=state.get("conversation_context", []),
        user_preferences=request.user_preferences, locale=request.locale,
    )
    result = await run_specialist(
        agent_name=agent_name, context=context, registry=registry,
        llm_client=_make_llm_client(settings), settings=settings,
    )
    rd = result.model_dump(mode="python")
    evidence = {eid: {"agent": agent_name} for eid in result.evidence_ids_used}
    return {"_agent_results": {agent_name: rd}, "evidence_by_id": evidence}


async def _node_synthesize(state: dict[str, Any]) -> dict[str, Any]:
    plan = state.get("supervisor_plan") or {}
    raw_results = state.get("_agent_results", {})
    agents_used = [a for a in plan.get("selected_agents", []) if a in raw_results]
    settings = get_agent_settings()

    if plan.get("needs_clarification"):
        return {"final_response": plan.get("clarifying_question")
                or "Bạn có thể bổ sung tiêu chí không?",
                "final_sources": [], "suggested_actions": ["Bổ sung ngân sách", "Bổ sung khu vực"]}
    if not agents_used:
        return {"final_response": "Xin chào! Tôi có thể giúp bạn tìm bất động sản, phân tích thị "
                "trường, hoặc tư vấn pháp lý. Bạn muốn tìm hiểu vấn đề gì?",
                "final_sources": [], "suggested_actions":
                ["Tìm bất động sản", "Phân tích thị trường", "Tư vấn pháp lý"]}

    # Collect sources (cards) + evidence.
    all_sources: list[AgentSource] = []
    deterministic_parts: list[str] = []
    for name in agents_used:
        rd = raw_results.get(name, {})
        if rd.get("content"):
            deterministic_parts.append(rd["content"])
        for src in rd.get("sources", []):
            if isinstance(src, dict):
                all_sources.append(AgentSource(**src))
    deterministic_response = "\n\n".join(deterministic_parts) or "Xin lỗi, chưa thể xử lý yêu cầu này."
    allowed_evidence_ids = set(state.get("evidence_by_id", {}).keys())

    llm_client = _make_llm_client(settings)
    generate_json = llm_client.generate_json if llm_client else None
    synth = await synthesize_final_answer(
        query=state["request"].message,
        conversation_context=state.get("conversation_context", []),
        agent_results=raw_results,
        deterministic_response=deterministic_response,
        default_actions=["Tìm bất động sản", "Phân tích thị trường", "Tư vấn pháp lý"],
        generate_json=generate_json,
        timeout_seconds=settings.AGENT_LLM_TIMEOUT_SECONDS,
        allowed_evidence_ids=allowed_evidence_ids,
        supervisor_plan=plan,
        evidence_by_id=state.get("evidence_by_id", {}),
    )

    final = synth.final_response
    if "legal_advisor" in agents_used and "không thay thế tư vấn luật sư" not in final.lower():
        final += "\n\n> ⚠️ Thông tin pháp lý chỉ mang tính tham khảo, không thay thế tư vấn luật sư."
    if "investment_advisor" in agents_used and "không phải lời khuyên tài chính" not in final.lower():
        final += "\n\n> ⚠️ Đây không phải lời khuyên tài chính."

    deduped = list({(s.type, s.id or s.url or s.title): s for s in all_sources}.values())
    return {"final_response": final, "final_sources": deduped,
            "suggested_actions": synth.suggested_actions[:5]}


def build_agentic_graph() -> CompiledStateGraph:
    graph = StateGraph(dict)
    graph.add_node("supervisor", _node_supervisor)
    graph.add_node("specialist", _node_specialist)
    graph.add_node("synthesize", _node_synthesize)
    graph.set_entry_point("supervisor")
    graph.add_conditional_edges("supervisor", _dispatch, ["specialist", "synthesize"])
    graph.add_edge("specialist", "synthesize")
    graph.add_edge("synthesize", END)

    settings = get_agent_settings()
    checkpointer = None
    if settings.AGENT_CHECKPOINT_ENABLED:
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            import os
            os.makedirs(os.path.dirname(settings.AGENT_CHECKPOINT_PATH) or ".", exist_ok=True)
            checkpointer = AsyncSqliteSaver.from_conn_string(settings.AGENT_CHECKPOINT_PATH)
        except Exception:
            checkpointer = None
    return graph.compile(checkpointer=checkpointer)
```

Also add a reducer for the merged dicts. Because `dict` state can't merge concurrent `Send` writes automatically, define the state with `Annotated` reducers. Replace `graph = StateGraph(dict)` with a `TypedDict` state:

```python
from typing import TypedDict


def _merge_dicts(a: dict, b: dict) -> dict:
    return {**(a or {}), **(b or {})}


class GraphState(TypedDict, total=False):
    request: Any
    conversation_context: list
    supervisor_plan: dict
    routing_filters: dict
    agents_used: list
    _agent_results: Annotated[dict, _merge_dicts]
    evidence_by_id: Annotated[dict, _merge_dicts]
    final_response: str
    final_sources: list
    suggested_actions: list
```
and use `StateGraph(GraphState)`.

Update `_initial_state` to seed `conversation_context` and the merge dicts:
```python
def _initial_state(request: AgentChatRequest) -> dict[str, Any]:
    return {
        "request": request,
        "conversation_context": _conversation_context(request),
        "supervisor_plan": {},
        "routing_filters": {},
        "agents_used": [],
        "_agent_results": {},
        "evidence_by_id": {},
        "final_response": "",
        "final_sources": [],
        "suggested_actions": [],
    }
```

Rewrite `run_agentic_graph` to read from the `ainvoke` return (not `aget_state`):
```python
async def run_agentic_graph(request: AgentChatRequest) -> AgentChatResponse:
    settings = get_agent_settings()
    started = time.perf_counter()
    graph = get_agentic_graph()
    config = {"configurable": {"thread_id": request.session_id, "checkpoint_ns": "agentic_chat"}}
    final_state = await graph.ainvoke(_initial_state(request), config)
    plan = final_state.get("supervisor_plan") or {}
    return AgentChatResponse(
        request_id=request.request_id,
        final_response=final_state.get("final_response", ""),
        agents_used=final_state.get("agents_used", []),
        sources=final_state.get("final_sources", []),
        suggested_actions=final_state.get("suggested_actions", []),
        trace_summary=TraceSummary(
            intent=plan.get("intent", "unknown"),
            agents=final_state.get("agents_used", []),
            source_count=len(final_state.get("final_sources", [])),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        ),
        full_trace={"graph_version": settings.AGENT_GRAPH_VERSION, "mode": "supervisor_specialist_fc"},
    )
```

- [ ] **Step 4: Add the dependency**

In `agent_service/requirements.txt`, add a line:
```
langgraph-checkpoint-sqlite>=2.0.0
```
Run: `pip install "langgraph-checkpoint-sqlite>=2.0.0"`
Expected: installs `langgraph-checkpoint-sqlite` and `aiosqlite` (already present).

- [ ] **Step 5: Run the new test**

Run: `python -m pytest agent_service/tests/test_supervisor_graph.py -q`
Expected: PASS (2 passed). If `Send` import path differs in langgraph 1.2.1, use `from langgraph.graph import Send` and re-run.

- [ ] **Step 6: Run the whole suite + compile check**

Run: `python -m pytest agent_service/tests -q`
Expected: PASS.
Run: `python -m compileall agent_service`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add agent_service/graph/agentic_workflow.py agent_service/requirements.txt agent_service/tests/test_supervisor_graph.py
git commit -m "feat: supervisor + specialist FC graph with grounded synthesis"
```

---

## Task 8: End-to-end agentic test with fakes (degradation + grounding)

**Files:**
- Test: `agent_service/tests/test_agentic_endtoend.py`

**Interfaces:**
- Consumes: `run_agentic_graph` (Task 7), `get_agentic_registry`.

- [ ] **Step 1: Write the test**

Create `agent_service/tests/test_agentic_endtoend.py`:

```python
from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph import agentic_workflow as wf
from agent_service.graph.router import RouterDecision


@pytest.mark.asyncio
async def test_degrades_to_retrieval_without_llm(monkeypatch):
    async def fake_route(state, client=None):
        return RouterDecision(intent="property_search", agents=["property_search"],
                              confidence=1.0, filters={"city": "HCM"})

    async def fake_hybrid(*, query, filters, parent_type, top_k, rerank_to):
        return [{"id": 7, "title": "Căn E", "price_text": "2 tỷ",
                 "area_text": "55 m²", "district": "Quận 3", "city": "HCM"}]

    monkeypatch.setattr(wf, "route_request", fake_route)
    monkeypatch.setattr("app.services.rag.hybrid_search.hybrid_search", fake_hybrid)
    monkeypatch.setattr(wf, "_make_llm_client", lambda settings: None)  # LLM unavailable
    # fresh registry bound to the patched hybrid_search
    monkeypatch.setattr(wf, "_registry", None, raising=False)

    resp = await wf.run_agentic_graph(AgentChatRequest(
        request_id="e1", session_id="s1", message="Tìm căn hộ Quận 3"))

    assert resp.agents_used == ["property_search"]
    assert resp.final_response                      # non-empty, retrieval-backed
    assert any(s.id == 7 for s in resp.sources)     # cards present, not crashed
```

- [ ] **Step 2: Run to verify it passes**

Run: `python -m pytest agent_service/tests/test_agentic_endtoend.py -q`
Expected: PASS. If the cached registry holds an old `hybrid_search` reference, ensure Step 1's `_registry = None` reset runs before `run_agentic_graph` (it does, via monkeypatch ordering).

- [ ] **Step 3: Commit**

```bash
git add agent_service/tests/test_agentic_endtoend.py
git commit -m "test: end-to-end agentic degradation and card rendering"
```

---

## Task 9: Wire investment_advisor at a basic level

**Files:**
- Modify: `agent_service/agents/investment_advisor_agent.py` (ensure `build_result` consumes market metrics into a basic scorecard) — verify first; only change if it returns a static string.
- Test: `agent_service/tests/test_investment_basic.py`

**Interfaces:**
- Consumes: `run_specialist`, `lookup_market_metrics` tool, `format_investment_scorecard` (optional, from `graph/synthesis.py`) or a minimal inline scorecard.

- [ ] **Step 1: Read the current build_result**

Run: `python -c "import inspect, agent_service.agents.investment_advisor_agent as m; print(inspect.getsource(m.InvestmentAdvisorAgent.build_result))"`
Expected: shows whether it incorporates `market_metrics` results or returns a static string.

- [ ] **Step 2: Write the failing test**

Create `agent_service/tests/test_investment_basic.py`:

```python
from __future__ import annotations

import pytest

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentContext, ToolDef
from agent_service.tools.registry import ToolRegistry
from agent_service.agents import fc_runner


@pytest.mark.asyncio
async def test_investment_uses_market_metrics_in_output():
    reg = ToolRegistry()
    reg.register(ToolDef(name="lookup_market_metrics", description="x",
                         parameters={"filters": "dict"}, required_params=["filters"],
                         allowed_for=["investment_advisor"]))

    async def _metrics(**kwargs):
        return {"status": "success",
                "results": [{"metric": "avg_price_per_m2", "value": 50,
                             "unit": "million VND/m2", "location": {"district": "Quận 7"}}],
                "evidence_ids": []}

    reg.bind("lookup_market_metrics", _metrics)
    ctx = AgentContext(agent_name="investment_advisor", query="đầu tư căn hộ Quận 7",
                       normalized_query="dau tu can ho quan 7",
                       routing_filters={"city": "HCM", "district": "Quận 7"})
    result = await fc_runner.run_specialist(
        agent_name="investment_advisor", context=ctx, registry=reg,
        llm_client=None, settings=get_agent_settings())
    assert result.status in {"completed", "no_evidence"}
    assert "50" in result.content or "Quận 7" in result.content   # data-driven, not static
    assert "lời khuyên tài chính" in result.content.lower()       # disclaimer retained
```

- [ ] **Step 3: Run to verify it fails (if currently static)**

Run: `python -m pytest agent_service/tests/test_investment_basic.py -q`
Expected: FAIL if `build_result` ignores `market_data` and returns the fixed string from `agentic_workflow._agent_build_result` style. (If it already passes, skip Step 4 and commit the test.)

- [ ] **Step 4: Make build_result data-aware (only if needed)**

In `agent_service/agents/investment_advisor_agent.py`, update `build_result` to read `action.tool_result["results"]` for `metric == "avg_price_per_m2"` and include a basic scorecard line (price/m², a simple yield note), always ending with the disclaimer `"> ⚠️ Đây không phải lời khuyên tài chính."`. Keep `status="no_evidence"` when no metrics were retrieved.

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest agent_service/tests/test_investment_basic.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent_service/agents/investment_advisor_agent.py agent_service/tests/test_investment_basic.py
git commit -m "feat: basic data-driven investment scorecard"
```

---

## Task 10: Remove dead deterministic helpers and final green

**Files:**
- Modify: `agent_service/graph/agentic_workflow.py` (delete leftover `_agent_think`, `_agent_build_result`, `_run_single_agent`, `_node_route`, `_route_after_route`, old `_node_dispatch_agents`, old `_node_synthesize`, `AgenticState` if unused)
- Verify: `agent_service/main.py` still imports `run_agentic_graph` / `run_agentic_graph_stream`

**Interfaces:**
- Produces: a single agentic implementation; no orphaned deterministic functions.

- [ ] **Step 1: Confirm nothing references the dead helpers**

Run: `grep -rn "_agent_think\|_agent_build_result\|_run_single_agent\|_route_after_route" agent_service --include=*.py`
Expected: matches only inside `agentic_workflow.py` (and possibly none after the rewrite). If a test references them, update the test.

- [ ] **Step 2: Delete the dead functions**

Remove the listed functions from `agent_service/graph/agentic_workflow.py`. Keep `run_agentic_graph_stream` (it may still reference `get_agentic_graph`; ensure it compiles — if it calls removed `_initial_state` keys, it already uses the new `_initial_state`).

- [ ] **Step 3: Compile + full suite**

Run: `python -m compileall agent_service`
Expected: no errors.
Run: `python -m pytest agent_service/tests -q`
Expected: PASS.

- [ ] **Step 4: Smoke-import the FastAPI app**

Run: `python -c "import agent_service.main as m; print(type(m.app).__name__)"`
Expected: `FastAPI`.

- [ ] **Step 5: Commit**

```bash
git add agent_service/graph/agentic_workflow.py
git commit -m "refactor: remove deterministic dead path from agentic workflow"
```

---

## Self-Review

**Spec coverage check (spec §→task):**
- §3 supervisor selective dispatch → Task 5 (context) + Task 7 (`_dispatch` via `Send`, subset).
- §4.2 specialist native-FC ReAct → Tasks 2, 3, 4.
- §4.3 Gemini FC + config footgun → Tasks 2, 2b.
- §4.5 grounded synthesis with plan/evidence_by_id/allowed_evidence_ids → Task 6 + Task 7 `_node_synthesize`.
- §4.6 investment basic wire → Task 9.
- §5 state + reducers → Task 7 `GraphState`.
- §6 multi-turn authoritative + AsyncSqliteSaver, non-stream reads from `ainvoke` → Tasks 5, 7.
- §7 degradation → Tasks 4 (fallback) + 8 (e2e no-LLM).
- §8 tests → each task is TDD; degradation/grounding in Tasks 6, 8.
- §11 acceptance → covered by Tasks 7, 8 assertions + final compile/suite (Task 10).
- D4 listing cards from sources → Task 4 (sources from build_result) + Task 7 (LLM never lists; cards from `final_sources`).

**Placeholder scan:** No "TBD"/"handle edge cases"/"write tests for the above" — every code step shows code; every test step shows the test.

**Type consistency:** `ToolLoopResult`/`ToolLoopStep` defined in Task 2 and consumed in Task 4; `run_specialist(*, agent_name, context, registry, llm_client, settings)` defined in Task 4 and called identically in Task 7; `synthesize_final_answer(..., supervisor_plan, evidence_by_id)` defined in Task 6 and called with those kwargs in Task 7; `_make_llm_client(settings)` defined in Task 7 and monkeypatched in Tasks 7/8; `RouterDecision` fields used consistently.

**Known risk to verify during execution:** exact `google-genai` 2.2.0 surface for `types.Part.from_function_response` and `response.function_calls`, and the `Send` import path in langgraph 1.2.1. Tasks 2 (Step 5) and 7 (Step 5) include explicit verification + fallback instructions.

---

## Out of scope (later milestones)

- Token-level streaming + frontend SSE consumption (frontend currently uses non-streaming `POST /chat`); `run_agentic_graph_stream` to be reworked then.
- Full committee multi-perspective investment analysis.
- Triage/deletion (vs quarantine) of the 13 orphaned test files from Task 1.
