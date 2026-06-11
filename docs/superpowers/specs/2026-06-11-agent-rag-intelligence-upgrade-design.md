# Agent RAG Intelligence Upgrade Design

## Goal

Improve answer quality and agent behavior after the public MVP hardening work is
in place. The upgrade adds LLM-assisted routing, query understanding,
memory-aware retrieval, optional LLM specialist synthesis, and stronger
grounding checks while preserving deterministic fallback behavior.

This spec assumes the hardening spec has already improved security,
observability, and controlled evaluation. The intelligence upgrade must remain
safe to disable at runtime.

## Current Context

The Agent Service currently uses a linear LangGraph workflow:

`context_builder -> readiness_checker -> router -> retrieval_planner -> specialist_agents -> synthesizer -> safety_validator -> memory_proposals`

The router is keyword-based. The retrieval planner extracts filters with regex
and creates independent retrieval tasks. Specialist agents consume assigned
evidence and produce deterministic text fragments. The synthesizer only exposes
sources backed by validated `evidence_ids_used`.

This is a strong grounded retrieval foundation, but it is closer to
multi-source RAG plus template synthesis than LLM-powered multi-agent reasoning.

## Non Goals

- Do not remove the current rule-based router.
- Do not remove deterministic specialist behavior.
- Do not bypass evidence validation in the synthesizer.
- Do not introduce a new public chat API contract.
- Do not require a live Gemini call for tests.
- Do not refactor `agent_service` away from backend imports in this spec.
- Do not add streaming responses.
- Do not add new crawler or embedding pipeline behavior.

## Design Principles

1. LLM behavior must be optional and feature-flagged.
2. Every LLM output must be schema-validated.
3. Invalid, low-confidence, or timed-out LLM outputs fall back to deterministic
   behavior.
4. User query text wins over memory. Memory can fill gaps but cannot override
   explicit current intent.
5. Sources must still come only from assigned evidence.
6. The system should become smarter without becoming less debuggable.

## Configuration

Add Agent Service settings:

- `AGENT_ROUTER_MODE: str = "rule"`
  - allowed: `rule`, `llm`, `hybrid`
- `AGENT_QUERY_REWRITE_ENABLED: bool = False`
- `AGENT_MEMORY_FILTERS_ENABLED: bool = False`
- `AGENT_SPECIALIST_LLM_ENABLED: bool = False`
- `AGENT_LLM_CONFIDENCE_THRESHOLD: float = 0.65`
- `AGENT_LLM_MAX_REWRITES: int = 3`
- `AGENT_LLM_ROUTER_TIMEOUT_SECONDS: float = 5.0`
- `AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS: float = 12.0`

Defaults keep current behavior unchanged.

## Scope

### 1. LLM-Assisted Router

Problem:

Keyword routing misses ambiguous or complex real estate questions. For example,
"co nen mua nha Quan 7 bay gio khong?" can be property search, market analysis,
and investment advice, not just property search.

Design:

Create a router module:

`agent_service/graph/router.py`

Public functions:

- `route_with_rules(state) -> RouterDecision`
- `route_with_llm(state, client) -> RouterDecision`
- `route_request(state, client=None) -> RouterDecision`

`RouterDecision` schema:

- `intent: str`
- `agents: list[str]`
- `confidence: float`
- `filters: dict[str, Any]`
- `needs_clarification: bool`
- `clarifying_question: str | None`
- `reason: str`
- `mode: "rule" | "llm" | "hybrid" | "fallback"`
- `warnings: list[StructuredWarning]`

Allowed agents:

- `property_search`
- `project_agent`
- `market_analysis`
- `news_agent`
- `legal_advisor`
- `investment_advisor`

Behavior:

- `rule` mode uses current keyword router.
- `llm` mode tries Gemini first and falls back to rules when invalid.
- `hybrid` mode runs rules and LLM, then merges:
  - include high-confidence LLM agents
  - keep rule agents when they match explicit domain keywords
  - default to `property_search` if both fail
- LLM output must be JSON. Invalid JSON triggers fallback.
- Unknown agent names are dropped and warned.
- Low confidence triggers fallback or merged rule result.
- Router trace records decision mode, confidence, selected agents, and warnings.

Prompt constraints:

- Vietnamese real estate domain.
- Return JSON only.
- Do not answer the user.
- Extract routing and filters only.
- Prefer multiple agents when the question mixes search, legal, market, and
  investment.

Tests:

- Rule mode returns current behavior.
- LLM mode accepts valid JSON and routes mixed query.
- LLM mode falls back on timeout, invalid JSON, unknown agent, low confidence.
- Hybrid mode merges explicit legal/property keywords with LLM investment
  intent.
- Conversation context can influence routing only when the current message is
  underspecified.

### 2. Query Understanding And Rewriting

Problem:

Current retrieval uses the original query and simple regex filters. Recall can
be weak for paraphrases, slang, and underspecified real estate language.

Design:

Create:

`agent_service/graph/query_understanding.py`

Schemas:

`QueryUnderstanding`

- `original_query: str`
- `normalized_query: str`
- `rewritten_query: str`
- `expanded_queries: list[str]`
- `filters: dict[str, Any]`
- `inferred_filters: dict[str, Any]`
- `missing_slots: list[str]`
- `warnings: list[StructuredWarning]`

Behavior:

- Start with deterministic extraction from current `_extract_filters`.
- If `AGENT_QUERY_REWRITE_ENABLED=true`, call Gemini to produce:
  - one canonical rewritten query
  - up to `AGENT_LLM_MAX_REWRITES` expanded queries
  - candidate filters
  - missing slots
- Validate filters against an allowlist:
  - `listing_type`
  - `property_type`
  - `city`
  - `district`
  - `ward`
  - `min_price`
  - `max_price`
  - `min_area`
  - `max_area`
  - `bedrooms`
- Query-extracted filters override LLM-inferred filters.
- Rewritten query is used for semantic retrieval only.
- Original query remains available to specialists and trace.

Retrieval planner integration:

- `build_retrieval_plan` should read `query_understanding` when present.
- Filters come from merged validated filters.
- Retrieval tasks can include `metadata` in trace even if `RetrievalTask` does
  not gain a new field. Avoid breaking the existing contract unless necessary.

Tests:

- Rewriter disabled preserves current behavior.
- Valid rewrite changes semantic query while keeping original query in trace.
- Invalid filters are dropped with warning.
- Current query filters override memory and LLM inferred filters.
- Expanded queries are capped by config.

### 3. Memory-Aware Retrieval

Problem:

User preferences are loaded and passed to the Agent Service, but they are not
deeply used to improve retrieval filters.

Design:

Create:

`agent_service/graph/memory_filters.py`

Function:

`derive_memory_filters(user_preferences, current_filters, query) -> MemoryFilterResult`

`MemoryFilterResult`:

- `filters: dict[str, Any]`
- `applied_keys: list[str]`
- `skipped_keys: list[str]`
- `warnings: list[StructuredWarning]`

Allowed preference mappings:

- `preferred_city` -> `city`
- `preferred_district` -> `district`
- `budget.max` or `max_budget` -> `max_price`
- `budget.min` or `min_budget` -> `min_price`
- `preferred_property_type` -> `property_type`
- `listing_type` -> `listing_type`
- `bedrooms` -> `bedrooms`

Precedence:

1. Explicit current query filter wins.
2. LLM-extracted current-query filter wins if validated.
3. Memory fills only missing filters.
4. Memory is skipped if it conflicts with current query.

Trace:

- Record memory-applied filters under:
  - `full_trace.query_understanding.memory_filters`
  - or retrieval planner step output
- Each applied filter must say which preference key produced it.

Tests:

- Preferred district fills missing district.
- Query district overrides preferred district.
- Budget memory fills max price only when query lacks price.
- Invalid memory values are skipped.
- Trace records applied and skipped memory keys.

### 4. Optional LLM Specialist Synthesis

Problem:

Specialist agents currently format evidence into deterministic text. This is
safe and fast, but it cannot synthesize nuanced comparisons or explain tradeoffs
well.

Design:

Keep existing specialist functions as deterministic fallback.

Add optional LLM synthesis per specialist behind
`AGENT_SPECIALIST_LLM_ENABLED=true`.

Create:

`agent_service/agents/llm_specialists.py`

Common output schema:

- `agent_name: str`
- `status: "completed" | "partial" | "no_evidence" | "failed" | "skipped"`
- `content: str`
- `claims: list[dict[str, Any]]`
- `evidence_ids_used: list[str]`
- `confidence: float | str | None`
- `warnings: list[StructuredWarning]`
- `missing_evidence: list[str]`

Prompt constraints:

- Answer in Vietnamese.
- Use only provided evidence.
- Cite evidence by `evidence_id`.
- Do not invent prices, legal status, ROI, yield, or market trends.
- If evidence is insufficient, say so.
- For legal content, include a professional legal advice disclaimer.
- For investment content, include financial risk disclaimer.
- Return JSON only.

Specialist-specific behavior:

Property:

- Compare listing fit against budget, location, area, and property type.
- Avoid claiming availability beyond evidence.

Legal:

- Distinguish listing-claimed legal status from legal KB evidence.
- Never say a property is legally safe unless evidence directly supports it.

Investment:

- Use market metrics when present.
- If yield cannot be calculated, state missing inputs.
- Separate evidence-backed observations from assumptions.

Market:

- Say current snapshot if no time series.
- Avoid trend claims unless news or historical metrics support them.

News:

- Summarize relevant articles and dates if available.

Project:

- Use project evidence and avoid developer reputation claims without sources.

Fallback:

- If LLM times out, returns invalid JSON, or references invalid evidence IDs,
  fall back to deterministic specialist result and add a warning.

Tests:

- LLM specialist valid JSON is accepted.
- Invalid JSON falls back.
- Hallucinated evidence id is rejected by synthesizer.
- Legal and investment prompts enforce disclaimers.
- No evidence returns deterministic no-evidence behavior.

### 5. Stronger Grounding And Safety Validation

Problem:

The synthesizer already validates `evidence_ids_used`, but LLM specialists add
new risks: unsupported claims, overconfident legal/financial statements, and
invalid citations.

Design:

Extend safety validation without making it a full moderation system.

Checks:

- Existing missing-source checks remain.
- If a source-backed agent returns content but uses no valid evidence, warning:
  `agent_answer_missing_valid_evidence`.
- If specialist output contains evidence IDs not assigned to that agent, warning:
  `invalid_evidence_reference`.
- Legal answers must include disclaimer phrase.
- Investment answers must include financial risk phrase.
- If LLM output has `claims`, each claim should include at least one valid
  evidence id, unless claim type is explicitly `caveat`, `disclaimer`, or
  `missing_evidence`.
- If too many invalid claims exist, downgrade status to `partial` or use
  fallback content.

Tests:

- Claim without evidence is warned.
- Caveat without evidence is allowed.
- Invalid evidence id is not exposed as source.
- Financial disclaimer missing warning is preserved.

### 6. Evaluation-Driven Rollout

Problem:

LLM features can improve answers but also increase cost and hallucination risk.

Design:

Use the evaluation system from the hardening spec to compare modes.

Add trace metadata:

- router mode
- query rewrite enabled
- memory filters enabled
- specialist mode
- model names
- prompt versions

Rollout:

1. Enable LLM router in admin/dev only.
2. Run eval on a fixed set of mixed queries.
3. Enable query rewriting if groundedness does not regress.
4. Enable memory filters for authenticated users only.
5. Enable LLM specialists for selected domains, starting with market or
   investment, then legal only after strong tests.

Acceptance score guidance:

- Groundedness should not drop below deterministic baseline.
- Citation quality must improve or remain equal.
- Safety must remain equal or improve.
- Helpfulness should improve for mixed/investment queries.

## Data Flow

1. Context builder normalizes query and collects conversation context.
2. Readiness checker reports source availability.
3. Router produces `RouterDecision` using configured mode.
4. Query understanding produces rewritten query, expanded queries, and filters.
5. Memory filters fill missing filters when enabled.
6. Retrieval planner builds tasks using merged filters and selected semantic
   query.
7. Retrieval executor creates evidence registry and assignment.
8. Specialist agents run deterministic or LLM mode.
9. Synthesizer validates used evidence and builds final sources.
10. Safety validator checks grounding and disclaimers.
11. Memory proposal node remains conservative.
12. Full trace includes router/query/memory/specialist mode metadata.

## Error Handling

- Gemini missing API key: fall back to deterministic behavior.
- Timeout: fall back and warn.
- Invalid JSON: fall back and warn.
- Unknown agent name: drop it and warn.
- Invalid filter: drop it and warn.
- Invalid evidence id: do not expose source; warn.
- LLM specialist failure: use deterministic specialist output.

## Testing Strategy

Focused test files:

- New `backend/tests/test_agent_llm_router.py`
- New `backend/tests/test_agent_query_understanding.py`
- New `backend/tests/test_agent_memory_filters.py`
- New `backend/tests/test_agent_llm_specialists.py`
- Existing `backend/tests/test_agent_graph_core.py`
- Existing `backend/tests/test_agent_retrieval_planner.py`
- Existing `backend/tests/test_agent_specialists.py`
- Existing `backend/tests/test_agent_evaluation.py`

Verification commands:

```powershell
python -m pytest backend\tests\test_agent_llm_router.py backend\tests\test_agent_query_understanding.py backend\tests\test_agent_memory_filters.py backend\tests\test_agent_llm_specialists.py backend\tests\test_agent_graph_core.py backend\tests\test_agent_retrieval_planner.py backend\tests\test_agent_specialists.py backend\tests\test_agent_evaluation.py -q
python -m compileall agent_service backend\app
```

Full regression before merge:

```powershell
python -m pytest backend\tests -q
python -m compileall backend\app agent_service pipeline_worker
docker compose config --services
```

## Conflict Avoidance

Implementation should touch only:

- `agent_service/config.py`
- `agent_service/graph/nodes.py`
- `agent_service/graph/router.py`
- `agent_service/graph/query_understanding.py`
- `agent_service/graph/memory_filters.py`
- `agent_service/graph/retrieval_planner.py`
- `agent_service/agents/specialists.py`
- `agent_service/agents/llm_specialists.py`
- `agent_service/llm/gemini.py` only for structured JSON helper improvements
- Agent tests listed above
- Backend mirror contracts only if response schema is additively extended

Do not touch:

- Listing routers/schemas/models
- Listing image migration or model
- Crawler modules
- Pipeline worker or Airflow
- Frontend listing pages/components
- Report files

## Rollout Plan

1. Refactor current rule router into a dedicated module without behavior change.
2. Add LLM router behind `AGENT_ROUTER_MODE`.
3. Add query understanding behind disabled feature flag.
4. Add memory filters behind disabled feature flag.
5. Add LLM specialist module behind disabled feature flag.
6. Extend grounding/safety checks.
7. Use eval to compare deterministic and LLM modes.
8. Enable features gradually in development, then staging, then production.

## Acceptance Criteria

- Default config preserves current deterministic behavior.
- LLM router improves mixed intent routing when enabled.
- Invalid LLM output never breaks chat.
- Query rewriting improves retrieval inputs while preserving original query in
  trace.
- Memory filters only fill missing values and never override explicit user
  request.
- LLM specialist answers expose only validated sources.
- Safety warnings catch unsupported legal/financial claims.
- Evaluation trace identifies which intelligence features were active.

## Risks

- LLM routing can increase cost and latency. Timeouts and fallback are required.
- Query rewriting can reduce precision if filters are inferred incorrectly.
  Filter allowlists and precedence rules reduce this risk.
- Memory-aware retrieval can feel surprising if not traceable. Applied memory
  filters must be visible in trace and admin views.
- LLM specialists can hallucinate. JSON schema validation and evidence ID checks
  are mandatory.
