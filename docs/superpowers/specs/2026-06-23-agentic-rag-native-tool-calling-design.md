# Agentic RAG Multi-Agent Rewrite — Native Tool-Calling

**Date:** 2026-06-23
**Status:** Design approved, pending spec review
**Scope:** `agent_service/` core graph rewrite. Backend/frontend contract unchanged this milestone.

---

## 1. Problem & Context

The live chat path (`agent_service/main.py` → `graph/agentic_workflow.py`) is advertised as
"agentic RAG with ReAct loops" but is in fact a **deterministic pipeline**:

- `_agent_think()` is hardcoded `if/else` — each agent calls one predetermined tool, then stops.
  No LLM reasoning, no real ReAct, no autonomous tool selection.
- Responses are **string templates**; `_node_synthesize` is `"\n\n".join(parts)` — no LLM synthesis,
  no grounding, no dedup. `investment_advisor` returns a static string regardless of data.
- A genuinely agentic layer already exists but is **dead code**: `agents/base.py` (`BaseAgent._llm_think`
  real ReAct), `agents/orchestrator.py` (round-based coordination + LLM synthesizer),
  `graph/synthesis.py` (`synthesize_final_answer` with evidence-id grounding validation),
  `committee.py`, `investment_model.py`. Confirmed via grep: nothing on the live path imports them.

Git history (`bb4b3c2` "migrate to LangGraph agentic RAG") shows the team replaced a working pure-Python
`OrchestratorAgent` with a LangGraph StateGraph to gain streaming/checkpoint/retry, but the migration
**reimplemented a dumbed-down deterministic version** and dropped the agentic behavior.

### Concrete defects to fix as part of this work

1. Multi-turn context dropped: `conversation_context` is received in the request and built by the
   backend, but `_node_route` calls `route_request({"request": request})` without it, and
   `_run_single_agent` builds `AgentContext` without `conversation_context`. Follow-up questions
   lose history.
2. Fake persistence: `build_agentic_graph()` uses `MemorySaver()` (RAM) despite the
   `AGENT_CHECKPOINT_PATH`/SQLite contract. Lost on restart; per-worker isolation.
3. Streaming depends implicitly on the checkpointer: `run_agentic_graph_stream` reads the final result
   via `graph.aget_state(config)`; with `AGENT_CHECKPOINT_ENABLED=False` this returns empty →
   empty `final_response`. (Streaming is out of scope this milestone, but the new design must not
   reproduce the coupling.)
4. Silent LLM disable: `GeminiClient.generate_text_with_usage` returns empty with
   `skipped_reason="gemini_model_not_configured"` unless `GEMINI_MODEL` is in `model_fields_set`
   (i.e. explicitly set in `.env`). Local runs without `GEMINI_MODEL` silently disable all LLM calls
   even with a valid API key.

### Goal

Make the system genuinely agentic: a **supervisor/planner** that selectively chooses specialists,
**specialist sub-agents** that reason with **native Gemini function-calling**, and a **grounded
synthesizer** that only states facts backed by retrieved evidence.

---

## 2. Decisions (locked)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Approach | **C** — rewrite with native Gemini function-calling |
| D2 | Topology | **Supervisor + specialist sub-agents (subgraphs)**, selective dispatch in parallel |
| D3 | Dispatch | Supervisor selects `selected_agents` from query + `conversation_context`; **only chosen** specialists run, fanned out in parallel via LangGraph `Send` |
| D4 | Listing UX | Listing **cards render from `sources`/`cards`** (images, price, link) on the frontend; the LLM writes **analysis/prose only** and never generates listing facts |
| D5 | Streaming | **Out of scope** this milestone — keep `POST /chat` non-streaming. Token streaming + frontend SSE is a later milestone |
| D6 | Multi-turn source of truth | **`conversation_context` from the backend is authoritative**; SQLite checkpoint is for resume/observability only, not the sole memory |
| D7 | Investment model | Wire `investment_model`/`committee` at a **basic level** only this milestone |

---

## 3. Architecture

```
AgentChatRequest
   │
   ▼
LangGraph StateGraph  (AsyncSqliteSaver, thread_id = session_id)
   │
   ├─ supervisor (plan)
   │     in:  original_query, conversation_context, user_preferences
   │     out: supervisor_plan { selected_agents[], filters, intent, reason,
   │                            needs_clarification?, clarifying_question? }
   │
   ├─ dispatch  (conditional)
   │     if needs_clarification or selected_agents == []  → synthesize
   │     else  Send(selected_agents) → run specialists IN PARALLEL
   │             ├─ property_search    (subgraph: native-FC ReAct)
   │             ├─ market_analysis     (subgraph)
   │             ├─ legal_advisor        (subgraph)
   │             ├─ investment_advisor   (subgraph)
   │             ├─ project_agent        (subgraph)
   │             └─ news_agent           (subgraph)
   │
   └─ synthesize (grounded)
         in:  original_query, conversation_context, supervisor_plan,
              agent_results, evidence_by_id, allowed_evidence_ids
         out: final_response (prose), sources/cards, suggested_actions
   ▼
AgentChatResponse  (contract unchanged)
```

### Selective dispatch examples (supervisor behavior)

| Query type | `selected_agents` |
|-----------|-------------------|
| Tìm listing ("cần hộ 2PN Q7 dưới 3 tỷ") | `[property_search]` |
| So sánh với thị trường ("giá này so với khu vực thế nào") | `[property_search, market_analysis]` |
| Pháp lý ("thủ tục sang tên sổ đỏ") | `[legal_advisor]` |
| Đầu tư ("mua căn này cho thuê có lời không") | `[property_search, market_analysis, investment_advisor]` |
| Tin tức ("thị trường BĐS tháng này") | `[news_agent]` |
| Dự án ("dự án Vinhomes Grand Park") | `[project_agent]` |

Supervisor modes follow existing `AGENT_ROUTER_MODE` (`rule | llm | hybrid`). The LLM planner returns
`selected_agents` + `filters`; rule fallback uses keyword matching (existing `route_with_rules`).
Empty selection from rules defaults to `[property_search]`.

---

## 4. Components

### 4.1 Supervisor / planner (`graph/router.py` evolved → planner)

- Input state: `original_query`, `conversation_context` (compact, last N turns), `user_preferences`,
  `locale`.
- Reuses `route_with_rules`, `route_with_llm`, `merge_router_decisions`, `sanitize_agents`.
- **New:** the LLM planner prompt receives `conversation_context` (currently `compact_context` is read
  but never populated — fix the wiring) so follow-ups resolve correctly.
- Output: `supervisor_plan` (superset of today's `RouterDecision`): `selected_agents`, `filters`,
  `intent`, `confidence`, `reason`, `needs_clarification`, `clarifying_question`, `warnings`.

### 4.2 Specialist subgraph (replaces `agents/base.py` ReAct + `_agent_think`)

Each specialist is a small ReAct loop using **native Gemini function-calling**:

1. **System prompt** = `_role_description(agent_name)` (reuse — e.g. `legal_advisor` always appends the
   "không thay thế luật sư" disclaimer and refuses out-of-domain).
2. Build `tools=[types.Tool(function_declarations=[...])]` containing **only** the tools the agent is
   `allowed_for` (existing `ToolRegistry.list_for_agent`). New adapter `tooldef_to_function_declaration`
   converts `ToolDef.parameters` into a proper JSON schema (`types.Schema`).
3. Call Gemini with `config=types.GenerateContentConfig(tools=..., tool_config=...)`.
4. If the response contains `function_call(s)` → execute via `ToolRegistry.call` (retry-wrapped) →
   append `functionResponse` parts to the running `contents` → loop (max `AGENT_MAX_ITERATIONS`,
   guarded by `AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS`).
5. When the model stops calling tools → its text is the specialist's analysis.
6. Return a standardized `AgentResult`: `content` (analysis), `sources` (structured records → cards),
   `evidence_ids_used`, `confidence`, `status`, `iterations`.

The per-domain `build_result` formatters (e.g. `property_search_agent.build_result` building listing
cards + `AgentSource` with images/url/price) are **retained** to produce structured `sources`.

### 4.3 Gemini client extension (`llm/gemini.py`)

- New `generate_with_tools(contents, tools, tool_config, timeout)` returning text + any function calls +
  usage. Keeps the existing semaphore, retry/backoff (400 vs 429), and cost tracking.
- **Fix D-defect 4:** drop / correct the `model_explicitly_configured` gate so a valid `GEMINI_API_KEY`
  is sufficient to run the LLM; do not silently skip when `GEMINI_MODEL` is merely a class default.

### 4.4 Tools (reuse, unchanged)

`tools/retrieval.py` (`search_listings/projects/articles` → `app.services.rag.hybrid_search`),
`tools/market.py` (`lookup_market_metrics/timeseries`), `tools/registry.py` (`allowed_for` already
enforced). `_attach_listing_images` retained for card images.

### 4.5 Grounded synthesizer (`graph/synthesis.py`, reuse `synthesize_final_answer`)

- **Signature inputs (per refinement):** `original_query`, `conversation_context`, `supervisor_plan`,
  `agent_results`, `evidence_by_id`, `allowed_evidence_ids`.
- The graph builds `evidence_by_id` (id → record/source) and `allowed_evidence_ids` (set) from all
  specialist tool results before synthesis.
- The synthesizer LLM produces Vietnamese prose; **every factual claim must cite an evidence_id in
  `allowed_evidence_ids`**. On invalid/missing grounding (`_invalid_grounding_warning`) or empty/invalid
  JSON → **fallback to deterministic concatenation** of specialist `content`.
- **The synthesizer never lists listings**: listing facts come only from `sources`/`cards`, which the
  frontend renders. `final_response` carries analysis/comparison/advice text.
- Reuse domain disclaimers (legal, investment) appended if absent.

### 4.6 Investment specialist (basic wire, D7)

`investment_advisor` specialist may call `lookup_market_metrics` and produce a basic ROI/yield-aware
analysis. Wire `investment_model`/`committee` only at a basic level (e.g. a single scorecard pass if
metrics available); full committee perspectives deferred.

---

## 5. State schema (graph)

```python
{
  "request": AgentChatRequest,
  "original_query": str,
  "conversation_context": list[ConversationContextItem],   # authoritative multi-turn (D6)
  "supervisor_plan": { selected_agents, filters, intent, confidence,
                       reason, needs_clarification, clarifying_question, warnings },
  "agent_results": dict[str, AgentResult],                  # merged from parallel Send branches
  "evidence_by_id": dict[str, dict],                        # evidence_id → record/source
  "allowed_evidence_ids": set[str],
  "agent_blackboard": {"entries": [...]},                   # reuse blackboard for traceability
  "final_response": str,
  "final_sources": list[AgentSource],
  "suggested_actions": list[str],
  "agents_used": list[str],
}
```

Parallel `Send` branches each write into `agent_results`/`evidence_by_id` via a reducer (merge dicts).

---

## 6. Multi-turn & checkpoint

- `conversation_context` (built by backend `app/services/chatbot/context.py`) is passed into graph state
  and threaded into both the supervisor prompt and each specialist context. **Authoritative.**
- `AsyncSqliteSaver` (add dependency `langgraph-checkpoint-sqlite`) with `thread_id=session_id`, path
  `AGENT_CHECKPOINT_PATH`. Used for resume/observability only. Replace `MemorySaver`.
- Non-streaming entry (`run_agentic_graph`) reads the result from the `ainvoke` return value directly —
  **not** from `aget_state` — so it does not depend on the checkpointer being enabled.

---

## 7. Error handling & degradation

- Specialist LLM fail/timeout/budget-exceeded → fall back to the specialist's **deterministic `think`**
  (one default tool) so retrieval still runs and produces evidence.
- Synthesizer LLM fail/invalid grounding → **deterministic concatenation** of specialist `content`.
- Tool call failure → retry (existing `with_retry`), then the specialist continues without that tool's
  evidence and may mark `missing_evidence`.
- Empty query → friendly greeting with suggested actions (existing behavior).
- All existing flags honored: `AGENT_ROUTER_MODE`, `AGENT_MAX_ITERATIONS`,
  `AGENT_SPECIALIST_LLM_ENABLED`, `AGENT_LLM_*_TIMEOUT_SECONDS`, cost/budget guard.
- The system must **degrade, never crash**: any node exception is caught and converted to a failed
  `AgentResult` / safe fallback response.

---

## 8. Testing (TDD)

Write tests first, with a **fake Gemini client** (returns scripted `function_call` then text) and
injected `httpx` transport so everything runs offline.

1. Specialist FC loop: model emits `function_call` → tool executed → model emits final text; assert
   `AgentResult.content` + `sources` + `evidence_ids_used`.
2. Specialist tool restriction: an agent only receives its `allowed_for` tools.
3. Supervisor selective dispatch: each example query in §3 selects the expected `selected_agents`;
   only those specialists run.
4. Multi-turn: `conversation_context` reaches the supervisor prompt and specialist context (follow-up
   like "thế còn quận 7?" inherits prior intent).
5. Grounded synthesis: a fabricated `evidence_id` not in `allowed_evidence_ids` → synthesizer output
   rejected → deterministic fallback; valid evidence → LLM prose passes.
6. Listing cards: `final_response` contains analysis but listing facts live in `sources`, not invented
   by the LLM.
7. Degradation: LLM disabled (no key / budget exceeded) → deterministic path still returns retrieval
   results; no crash.
8. Gemini config fix: valid `GEMINI_API_KEY` without explicit `GEMINI_MODEL` still runs the LLM.

Update/remove existing tests that assert the deterministic `_agent_think` behavior. Keep
`agent_service/tests/conftest.py` offline-injection pattern.

---

## 9. Reuse vs rewrite inventory

| Action | Modules |
|--------|---------|
| **Reuse as-is** | `contracts.py`, `tools/retrieval.py`, `tools/market.py`, `tools/registry.py`, `app.services.rag.hybrid_search`, `llm/cost.py`, `graph/blackboard.py`, `graph/synthesis.py`, `tools/readiness.py`, `evaluation/judge.py` |
| **Extend** | `llm/gemini.py` (native FC + config fix), `graph/router.py` (planner + conversation_context wiring), specialist `build_result` formatters, `committee.py`/`investment_model.py` (basic wire) |
| **Rewrite** | `graph/agentic_workflow.py` → new supervisor/specialist graph; `agents/base.py` ReAct → native-FC agent node |
| **Delete** | deterministic `_agent_think`, `_agent_build_result`, `_node_synthesize` concat-only path |
| **Add dependency** | `langgraph-checkpoint-sqlite` |

---

## 10. Out of scope (later milestones)

- Token-level streaming + frontend SSE consumption (frontend currently uses non-streaming `POST /chat`).
- Full committee multi-perspective investment analysis.
- Removing legacy duplicate agent layers beyond what this rewrite consolidates.

---

## 11. Acceptance criteria

- A query routed to a specialist triggers **real LLM tool-calling** (verifiable in trace: model chose
  the tool, not a hardcoded branch).
- Supervisor selects a **subset** of agents per query (not all 6) matching §3 examples.
- `final_response` is **LLM-synthesized prose grounded in evidence**; fabricated facts are rejected.
- Listing cards still render (images/price/link) from `sources`.
- Follow-up questions use prior conversation context.
- With LLM unavailable, the system degrades to retrieval + deterministic formatting without crashing.
- `python -m pytest agent_service/tests -q` passes; `python -m compileall agent_service` clean.
