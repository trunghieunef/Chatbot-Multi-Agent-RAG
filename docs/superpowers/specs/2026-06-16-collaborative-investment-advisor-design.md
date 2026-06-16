# Collaborative Investment Advisor Design

## Goal

Evolve the current multi-agent real-estate chatbot into a collaborative
agentic system, starting with an investment-advisory workflow. The first phase
adds a financial model and a dedicated committee review node while preserving
the current grounded retrieval, deterministic fallback, and evidence validation
principles.

The target user experience is a fast investment scorecard followed by an
actionable checklist. The system should calculate useful metrics immediately
with clearly disclosed default assumptions, then ask the user to confirm or
adjust the key inputs.

## Current Context

The Agent Service already has a LangGraph workflow with context building,
readiness checks, routing, query understanding, retrieval planning, parallel
specialists, synthesis, safety validation, memory proposals, and an optional
ReAct-style retrieval retry loop. It also has evidence contracts, source
validation, deterministic investment calculations, and standalone
`agent_service/tests`.

This gives the project a strong base for collaboration. The missing layer is a
shared blackboard and a structured committee step that lets multiple agents
contribute to one investment decision instead of simply concatenating specialist
responses.

## Scope

Build the first collaborative vertical:

- Use case: investment analysis for a property or project opportunity.
- Output: short scorecard plus action checklist.
- Data persistence: store structured investment payloads in trace/chat metadata
  first, but design the contract so it can later become a `DealReview` entity.
- Collaboration style: dedicated committee node, not logic hidden inside the
  existing investment specialist.

## Non Goals

- Do not create a new `DealReview` database table in this phase.
- Do not build a frontend deal-review workspace yet.
- Do not require live LLM calls for tests.
- Do not bypass existing evidence validation.
- Do not replace deterministic fallbacks.
- Do not implement multi-round autonomous debate in the first phase.
- Do not change crawler, embedding, or ingestion behavior.

## Architecture

Add a collaborative investment path to the existing graph:

```text
router
  -> query_understanding
  -> retrieval_planner
  -> specialist_agents
  -> investment_model
  -> committee_review
  -> synthesizer
  -> safety_validator
  -> memory_proposals
```

The new nodes are:

- `investment_model_node`: builds an investment case, resolves assumptions, and
  calculates financial metrics.
- `committee_review_node`: reads the shared blackboard, investment case,
  assumptions, metrics, and warnings, then emits structured perspectives and a
  recommendation.

The existing `investment_advisor` specialist remains useful. It contributes
investment-specific notes to the blackboard, but final collaborative judgment
belongs to the committee node.

## State Contract

Extend `AgentGraphState` additively:

```python
agent_blackboard: dict[str, Any]
investment_case: dict[str, Any]
investment_assumptions: dict[str, Any]
investment_metrics: dict[str, Any]
committee_review: dict[str, Any]
```

### `agent_blackboard`

The blackboard is a shared append-only workspace for agents and nodes.

Each entry should follow this shape:

```python
{
    "id": str,
    "author": str,
    "type": str,
    "content": dict | str,
    "evidence_ids": list[str],
    "confidence": "low" | "medium" | "high",
    "created_at_step": str,
}
```

The committee reads the blackboard instead of scraping final prose from
specialist responses.

### `investment_case`

The investment case summarizes the target and available evidence:

```python
{
    "case_scope": "single_listing" | "area_screening" | "project_screening",
    "target": dict,
    "property_summary": dict,
    "market_summary": dict,
    "legal_summary": dict,
    "project_summary": dict,
    "news_summary": dict,
    "evidence_ids": list[str],
    "missing_evidence": list[str],
}
```

Every factual summary must include evidence back-links through `evidence_ids`.

### `investment_assumptions`

Each assumption must be structured:

```python
{
    "value": int | float | str | None,
    "unit": str,
    "source": "user" | "preference" | "default" | "estimated" | "derived",
    "depends_on": list[str],
    "evidence_ids": list[str],
    "note": str,
}
```

Rules:

- Ratios must use `0-1` units, not percentages. For example,
  `loan_ratio=0.6`, `interest_rate_annual=0.1`,
  `operating_cost_ratio=0.08`.
- `derived` means the value is directly computed from another known value or
  assumption, such as `loan_amount = purchase_price * loan_ratio`; it must
  include `depends_on` references to the source assumption keys, metric keys, or
  evidence IDs.
- Defaults are allowed, but must be disclosed in the final response.
- User-provided values override preferences and defaults.

Initial default assumptions:

- `equity_ratio`: `0.4`
- `loan_ratio`: `0.6`
- `interest_rate_annual`: configurable, default `0.1`
- `loan_term_years`: configurable, default `20`
- `vacancy_months_per_year`: configurable, default `1`
- `operating_cost_ratio`: configurable, default `0.08`
- `expected_monthly_rent`: user value if supplied; otherwise estimated or left
  missing depending on available evidence.

### `investment_metrics`

Each metric must include dependencies:

```python
{
    "value": int | float | str | None,
    "unit": str,
    "depends_on": list[str],
    "formula": str,
    "confidence": "low" | "medium" | "high",
    "warnings": list[str],
}
```

`depends_on` can reference assumption keys, metric keys, or evidence IDs.

Initial metrics:

- `price_per_m2`
- `market_price_delta`
- `loan_amount`
- `monthly_payment_estimate`
- `gross_yield`
- `net_yield`
- `monthly_cashflow_estimate`
- `cash_on_cash_return`

Metrics that depend heavily on default or estimated assumptions cannot receive
`high` confidence.

### `committee_review`

Committee output should be structured, not raw text:

```python
{
    "perspectives": list[Perspective],
    "recommendation": {
        "decision": "consider" | "wait" | "avoid" | "need_more_info",
        "confidence": "low" | "medium" | "high",
        "rationale": str,
        "required_confirmations": list[str],
    },
}
```

`Perspective` shape:

```python
{
    "role": "bull" | "bear" | "legal_risk" | "market_risk" | "finance" | "missing_inputs",
    "stance": "positive" | "negative" | "neutral" | "unknown",
    "summary": str,
    "claims": list[dict],
    "evidence_ids": list[str],
    "depends_on": list[str],
    "confidence": "low" | "medium" | "high",
    "risk_level": "low" | "medium" | "high" | "unknown",
    "suggested_actions": list[str],
}
```

## Data Flow

1. Router selects `investment_advisor` for investment queries.
2. Retrieval planner gathers property and market evidence by default.
3. Retrieval planner adds legal, project, or news evidence when the query or
   selected agents require those domains.
4. Specialist agents run and write structured blackboard entries.
5. `investment_model_node` builds `investment_case`.
6. `investment_model_node` resolves assumptions from user input, preferences,
   evidence, defaults, and derived calculations.
7. `investment_model_node` calculates metrics with dependency metadata.
8. `committee_review_node` creates structured perspectives and a recommendation.
9. Synthesizer produces a short scorecard, metric summary, assumption
   disclosure, and action checklist.
10. Safety validator checks evidence references, legal and financial
   disclaimers, unsupported claims, and confidence downgrades.
11. Trace/chat metadata stores `investment_case`, `investment_assumptions`,
   `investment_metrics`, `committee_review`, and blackboard entries.

## Output Shape

The final chat answer should favor this order:

1. Investment scorecard:
   - overall decision
   - confidence
   - key metrics
   - top upside
   - top risks
2. Assumption disclosure:
   - user-provided values
   - defaults or estimates used
   - values that need confirmation
3. Committee summary:
   - bull case
   - bear case
   - legal risk
   - market/finance risk
4. Action checklist:
   - confirm rent expectation
   - confirm loan terms
   - verify legal documents
   - compare market benchmark
   - inspect project/news signals when relevant

The response must clearly state that the investment analysis is not financial
advice.

## Error Handling And Safety

- If listing price or area is missing, skip price-per-square-meter, yield, and
  cashflow metrics; recommendation should usually be `need_more_info`.
- If expected rent is missing, use a disclosed default or estimate only when
  configured. Yield and cashflow confidence must be at most `medium`.
- If market benchmark is missing, financial metrics may still be calculated,
  but `market_risk` must mention the missing benchmark.
- If legal evidence is missing, legal perspective must not say the property is
  safe. It should require document verification.
- If too many assumptions are default or estimated, committee recommendation
  cannot be `consider` with `high` confidence.
- If committee LLM output is invalid or cites invalid evidence, fall back to a
  deterministic committee review.
- Final sources must still come only from validated evidence IDs.
- Investment output must include a financial-risk disclaimer.

## Deterministic Fallback

The first implementation should include deterministic builders for:

- investment case
- assumption resolution
- metric calculations
- committee perspectives

Optional LLM committee behavior can be added later behind a feature flag, using
the deterministic committee as fallback.

## Persistence Strategy

Phase one stores structured investment artifacts in trace/chat metadata only:

- `full_trace.agent_blackboard`
- `full_trace.investment_case`
- `full_trace.investment_assumptions`
- `full_trace.investment_metrics`
- `full_trace.committee_review`

The contract is deliberately shaped so these payloads can later be promoted to
a persistent `DealReview` table with version history.

## Testing Strategy

Add focused tests for:

- assumption resolver precedence: user > preference > evidence-derived >
  default.
- ratio units are stored as `0-1`.
- derived assumptions include `depends_on` or evidence/assumption references.
- financial metrics include `depends_on`.
- missing price/area skips dependent metrics.
- missing rent lowers yield and cashflow confidence.
- missing market benchmark creates a market-risk perspective.
- missing legal evidence creates a legal-risk perspective without claiming
  legal safety.
- deterministic committee fallback emits `perspectives: list[Perspective]`.
- graph trace includes investment artifacts.
- final response includes scorecard, checklist, assumption disclosure, and
  financial disclaimer.

Focused verification command:

```powershell
python -m pytest agent_service/tests/test_investment_*.py agent_service/tests/test_committee_review.py -q
```

Broader regression:

```powershell
python -m pytest agent_service/tests -q
python -m compileall agent_service backend\app
```

## Rollout Plan

1. Add state fields and blackboard helpers without changing graph behavior.
2. Add deterministic investment assumption and metric modules.
3. Add `investment_model_node` behind investment intent only.
4. Add deterministic `committee_review_node`.
5. Add trace serialization for investment artifacts.
6. Update synthesis to prefer scorecard plus checklist when committee review is
   present.
7. Add optional feature flag for committee LLM behavior in a later phase.
8. Promote trace metadata to a `DealReview` entity only after the chat workflow
   proves useful.

## Acceptance Criteria

- Investment queries return a scorecard plus action checklist.
- Default assumptions are disclosed and traceable.
- Every investment metric has dependency metadata.
- Committee review is a dedicated graph node.
- Committee perspectives are structured, not raw text.
- Evidence summaries include evidence ID back-links.
- Final answer never exposes unvalidated sources.
- Missing legal, market, price, area, or rent data lowers confidence or asks for
  more information.
- Structured artifacts are available in trace/chat metadata and can later be
  promoted to `DealReview`.
