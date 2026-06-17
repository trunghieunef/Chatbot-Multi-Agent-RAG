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

## Cost Estimation & Budget

Adding LLM calls to the agent pipeline increases operational cost. This section
provides a concrete estimate so the team can budget before rollout.

### Per-request LLM call breakdown

| Feature | Calls per request | Input tokens (est.) | Output tokens (est.) |
|---------|-------------------|---------------------|---------------------|
| Router (LLM mode) | 1 | ~600 | ~150 |
| Query understanding | 1 | ~500 | ~250 |
| Specialist (per agent) | 1 per agent | ~2 000 | ~500 |

### Gemini pricing assumptions

Pricing and rate limits change over time. The scenario table below is only a
planning estimate, not a source of truth for implementation.

Implementation requirements:

- Before enabling any LLM feature, choose a currently supported Gemini model
  from the official docs and update `GEMINI_MODEL` / `GEMINI_JUDGE_MODEL` env
  values accordingly.
- Do **not** rely on the current code default `gemini-2.0-flash`; Gemini 2.0
  Flash was shut down on June 1, 2026.
- Refresh input/output token prices from:
  https://ai.google.dev/gemini-api/docs/pricing
- Refresh RPM/TPM/RPD limits from:
  https://ai.google.dev/gemini-api/docs/rate-limits

### Monthly cost scenarios (1 000 chats/day, 30 days)

| Scenario | LLM calls/chat | Cost/chat | Cost/month |
|----------|---------------|-----------|------------|
| Deterministic only (current) | 0 | $0 | $0 |
| LLM router only | 1 | ~$0.0001 | ~$3 |
| Router + query rewrite | 2 | ~$0.0003 | ~$9 |
| Router + rewrite + 2 specialists | 4 | ~$0.003 | ~$90 |
| Full LLM (6 specialists) | 8 | ~$0.006 | ~$180 |
| Full LLM at 5 000 chats/day | 8 | ~$0.006 | ~$900 |

### Budget cap

Add a configurable monthly budget cap to prevent runaway costs:

- `AGENT_LLM_MONTHLY_BUDGET_USD: float = 100.0`
- `AGENT_LLM_COST_TRACKING_ENABLED: bool = True`

Behavior:

- Track estimated cost per request using token counts from the Gemini API
  response metadata (`usageMetadata` or equivalent). If the API does not
  return usage data, estimate from input/output character counts with a
  conservative multiplier.
- Accumulate monthly cost in a Redis key (e.g. `agent:llm:cost:2026-06`).
  **Use Redis only** to avoid a new database migration for cost tracking.
- When monthly budget is exceeded:
  - Log a warning.
  - Fall back all LLM features to deterministic mode.
  - Continue serving requests deterministically (never reject chat due to
    budget).
- Reset the counter on the 1st of each month.
- Expose current monthly cost via `/admin/agent-health` by adding an
  `llm_cost` field to the existing backend response. Keep the current `items`
  list unchanged. The backend can obtain the cost summary from an additive Agent
  Service health payload or, if that is unavailable, from the same Redis key.

## Latency Budget & Early Termination

Adding LLM calls also increases response latency. Without a total latency cap,
the worst-case chat response can exceed 20 seconds, which is unacceptable for
chat UX.

### Worst-case latency breakdown

| Step | Deterministic | LLM-enabled |
|------|--------------|-------------|
| context_builder | ~5 ms | ~5 ms |
| readiness_checker | ~10 ms | ~10 ms |
| router | ~1 ms (rule) | ~5 000 ms (LLM timeout) |
| query_understanding | ~5 ms (regex) | ~3 000 ms (LLM) |
| retrieval_planner | ~100 ms | ~100 ms |
| specialist_agents (sequential loop) | ~20 ms | ~12 000 ms (per-agent timeout) |
| synthesizer | ~10 ms | ~10 ms |
| safety_validator | ~10 ms | ~50 ms (with claim checks) |
| memory_proposals | ~5 ms | ~5 ms |
| **Total worst case** | **~166 ms** | **~20 180 ms** |

### Total latency budget

Add a hard cap on total agent graph execution time:

- `AGENT_TOTAL_TIMEOUT_SECONDS: float = 10.0`

Behavior:

- Wrap `chat_graph.ainvoke()` in an `asyncio.wait_for()` with the total timeout.
- If the graph exceeds the total timeout:
  - Cancel remaining LLM calls via task cancellation.
  - **Do not** attempt to collect partial results — `ainvoke()` does not
    return partial state on `asyncio.TimeoutError`. Instead, fall back to
    deterministic behavior for the entire request.
  - The deterministic fallback **must** run with all LLM feature flags
    force-disabled (`AGENT_ROUTER_MODE=rule`,
    `AGENT_QUERY_REWRITE_ENABLED=false`,
    `AGENT_SPECIALIST_LLM_ENABLED=false`) to avoid re-entering the same LLM
    graph and timing out a second time.
  - The forced deterministic fallback must be request-scoped. Do not mutate
    cached settings, environment variables, or global config because concurrent
    requests may still be using LLM mode. Pass a runtime override such as
    `force_deterministic=True` through the graph execution path.
  - Add warning `agent_total_timeout_exceeded` to trace.
  - If deterministic fallback also times out, return the existing safe
    fallback response ("He thong dang ban, vui long thu lai sau").
- If true partial-result support is desired in the future, it requires
  LangGraph streaming (`astream_events`) or a checkpointing backend
  (SqliteSaver/PostgresSaver). This is out of scope for the current spec.
- The total timeout is enforced at the `run_agent_graph` level.

### Per-feature timeouts (existing + new)

| Feature | Config key | Default |
|---------|-----------|---------|
| Router LLM | `AGENT_LLM_ROUTER_TIMEOUT_SECONDS` | 5.0 s |
| Query understanding | `AGENT_LLM_QUERY_TIMEOUT_SECONDS` | 5.0 s |
| Specialist LLM (per agent) | `AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS` | 12.0 s |
| Total graph execution | `AGENT_TOTAL_TIMEOUT_SECONDS` | 10.0 s |

Design rule: individual timeouts must sum reasonably within the total budget.
When `AGENT_SPECIALIST_LLM_ENABLED=true` with many agents, the per-agent timeout
should be lowered or the total timeout raised intentionally.

Implementation note on specialists: the current `specialist_agents_node` loops
sequentially over `agents_to_run`. If parallel execution is desired, the node
must be refactored to use `asyncio.gather` with per-agent timeouts. This is a
separate implementation task and is not required for the LLM specialist feature
to work correctly.

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
- `AGENT_LLM_QUERY_TIMEOUT_SECONDS: float = 5.0`
- `AGENT_TOTAL_TIMEOUT_SECONDS: float = 10.0`
- `AGENT_LLM_MONTHLY_BUDGET_USD: float = 100.0`
- `AGENT_LLM_COST_TRACKING_ENABLED: bool = True`

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
  - Include LLM agents with confidence >= `AGENT_LLM_CONFIDENCE_THRESHOLD`
    (default 0.65).
  - Keep rule agents when they match explicit domain keywords, regardless of
    LLM confidence.
  - If LLM and rule both select the same agent, deduplicate to a single entry
    and use the higher confidence value.
  - If rule produces agents that LLM did not select but those agents match
    explicit domain keywords (see `KEYWORDS_BY_AGENT`), keep them.
  - Default to `property_search` if both rule and LLM produce empty agent
    lists.
  - Set `mode = "hybrid"` and record which agents came from which source in
    `reason`.
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
  underspecified (defined as: normalized query length < 15 characters OR no
  keyword match in `KEYWORDS_BY_AGENT` after accent stripping).

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
- In the first implementation, use only `rewritten_query` for semantic
  retrieval.
- Store `expanded_queries` in trace for future evaluation only. Multi-query
  retrieval and result merging are out of scope for this spec.
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
- If too many invalid claims exist (more than 30% of claims lack valid evidence
  and are not typed `caveat`, `disclaimer`, or `missing_evidence`), downgrade
  status to `partial` and use fallback deterministic content for that agent.

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
- Gemini rate limit (HTTP 429): wait 1 second and retry once. If still 429,
  fall back to deterministic behavior and warn `gemini_rate_limited`.
- Monthly budget exceeded: fall back all LLM features, log warning, continue
  serving deterministically.

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
- New `backend/tests/test_agent_llm_cost_budget.py`
- New `backend/tests/test_agent_total_timeout.py`

Verification commands:

```powershell
python -m pytest backend\tests\test_agent_llm_router.py backend\tests\test_agent_query_understanding.py backend\tests\test_agent_memory_filters.py backend\tests\test_agent_llm_specialists.py backend\tests\test_agent_llm_cost_budget.py backend\tests\test_agent_total_timeout.py backend\tests\test_agent_graph_core.py backend\tests\test_agent_retrieval_planner.py backend\tests\test_agent_specialists.py backend\tests\test_agent_evaluation.py -q
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
- `agent_service/llm/cost.py` for Redis-backed monthly budget tracking
- `agent_service/llm/gemini.py` only for structured JSON helper improvements
- `agent_service/main.py` only for additive health payload fields if backend
  reads cost through Agent Service health
- `backend/app/services/agent_service/client.py` only for the additive health
  payload if backend reads cost through Agent Service health
- `backend/app/routers/admin.py` only to expose current monthly LLM cost in the
  existing `/admin/agent-health` response
- `backend/tests/test_admin_observability.py` or an equivalent admin test only
  for the additive cost summary
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
2. Add cost tracking infrastructure (token counting, monthly counter, budget
   check). Deploy and monitor for one week before enabling any LLM features.
3. Add total latency budget enforcement (`AGENT_TOTAL_TIMEOUT_SECONDS`).
4. Add LLM router behind `AGENT_ROUTER_MODE`.
5. Add query understanding behind disabled feature flag.
6. Add memory filters behind disabled feature flag.
7. Add LLM specialist module behind disabled feature flag.
8. Extend grounding/safety checks.
9. Use eval to compare deterministic and LLM modes.
10. Enable features gradually: dev → staging → production, monitoring cost and
    latency at each stage.

## Acceptance Criteria

- Default config preserves current deterministic behavior.
- Cost tracking reports estimated or provider-reported monthly token usage via
  admin API. Token counts come from Gemini `usageMetadata` when available,
  falling back to conservative character-based estimation.
- Monthly budget cap triggers deterministic fallback without rejecting chat.
- Total graph execution stays within `AGENT_TOTAL_TIMEOUT_SECONDS`; exceeded
  timeout triggers deterministic fallback, not an error.
- LLM rollout uses a currently supported Gemini model; no enabled environment
  points to deprecated `gemini-2.0-flash`.
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

- **Cost**: LLM routing can increase cost and latency. Timeouts and fallback are
  required. Monthly budget cap (`AGENT_LLM_MONTHLY_BUDGET_USD`) is the primary
  safeguard against runaway spending. Cost must be monitored weekly during
  rollout.
- **Latency**: Full LLM pipeline worst case exceeds 20 seconds.
  `AGENT_TOTAL_TIMEOUT_SECONDS` (default 10 s) prevents unbounded waits.
  Timeout triggers deterministic fallback, not a partial response (see
  implementation note in Latency Budget section). Per-feature timeouts must
  be tuned so they sum within the total budget.
- **Gemini rate limits**: Rate limits depend on model, project, usage tier, and
  active quota. During implementation, verify current RPM/TPM/RPD in AI Studio
  or official Gemini docs. At 8 LLM calls/chat and peak load, the agent service
  may hit rate limits. A retry-on-429 with deterministic fallback mitigates
  this. Monitor Gemini 429 responses via trace warnings.
- Query rewriting can reduce precision if filters are inferred incorrectly.
  Filter allowlists and precedence rules reduce this risk.
- Memory-aware retrieval can feel surprising if not traceable. Applied memory
  filters must be visible in trace and admin views.
- LLM specialists can hallucinate. JSON schema validation and evidence ID checks
  are mandatory. The 30% invalid-claim threshold triggers deterministic
  fallback.
