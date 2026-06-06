# Agent Service Grounded Retrieval Design

## Context

The current data pipeline already publishes crawled data into PostgreSQL parent
tables and indexes semantic chunks in `chunks.embedding` with BGE-M3 1024
dimension vectors. The backend fallback chatbot can call `hybrid_search()`
directly, but the production `agent_service` LangGraph path does not yet wire
real retrieval evidence into specialist agents.

This design completes the production path by making `agent_service` a grounded
multi-agent RAG system. The backend `/api/v1/chat` remains the public boundary.
The change is focused on the internal Agent Service graph, retrieval planning,
evidence contracts, and synthesis behavior.

## Goals

- Connect real pipeline data from `listings`, `projects`, `articles`, and
  `chunks` into `agent_service`.
- Centralize retrieval in the graph planner so specialist agents do not run
  duplicate searches.
- Support mixed queries with domain-specific retrieval and evidence sharing.
- Preserve provenance from retrieval task to evidence to final source.
- Prevent hallucinated listings, legal conclusions, and market/investment
  metrics when supporting evidence is absent.
- Keep compatibility with existing backend chat response contracts and frontend
  source rendering as much as possible.

## Non-Goals

- Do not change crawler behavior or CSV schemas.
- Do not add new database tables.
- Do not replace PostgreSQL + pgvector with another vector store.
- Do not implement a new frontend chat UI.
- Do not require project/news retrieval for every investment query.
- Do not create fake semantic chunks for market aggregates.

## Section 1: Architecture

Use the planner-first approach. `router_node` keeps responsibility for deciding
`agents_to_run`, while `retrieval_planner_node` becomes the only graph node that
creates and executes retrieval work.

Target graph flow:

```text
context_builder
  -> readiness_checker
  -> router
  -> retrieval_planner
  -> specialist_agents
  -> synthesizer
  -> safety_validator
  -> memory_proposals
```

`retrieval_planner_node` will:

1. Read `request.message`, `agents_to_run`, `readiness`, `user_preferences`,
   `routing_filters`, and `conversation_context`.
2. Build domain-specific retrieval tasks.
3. Execute tasks whose sources are ready.
4. Normalize raw records into evidence.
5. Store evidence in a single registry.
6. Assign evidence IDs to agents.
7. Record structured warnings and retrieval trace events.

Specialist agents consume evidence only through assigned evidence IDs. They do
not query the database or call retrieval tools themselves.

## Section 2: Data Contracts And Evidence Mapping

The implementation should reuse and extend existing contracts where possible:

- `agent_service.contracts.AgentSource`
- `agent_service.contracts.AgentChatResponse`
- `agent_service.graph.state.AgentGraphState`
- existing specialist result dicts

Avoid creating a parallel contract system when an existing model can be safely
extended.

### Evidence Domain And Source Type

Separate the purpose/domain of evidence from its physical source type:

```python
domain = "property" | "project" | "news" | "legal" | "market"
source_type = "listing" | "project" | "article" | "market_metric"
```

Legal and news evidence may both come from `articles`, but they have different
domains.

### Evidence Contract

Target shape:

```python
Evidence = {
    "evidence_id": str,
    "retrieval_task_id": str,
    "domain": str,
    "source_type": str,
    "source_identity": str,
    "record": dict,
    "facts": dict,
    "source": dict,
    "matched_chunks": list[MatchedChunk],
    "retrieved_for": list[str],
    "assigned_to": list[str],
    "warnings": list[StructuredWarning],
}
```

`record` keeps the raw `hybrid_search()` output for compatibility. Specialist
agents should prefer `facts` and `source` over raw records.

Listing facts should use explicit claim language:

```python
{
    "title": "...",
    "price": 4800000000,
    "area": 75,
    "price_per_m2": 64000000,
    "location": {...},
    "legal_status_claimed": "So hong",
}
```

`legal_status_claimed` is only a listing publisher claim. It is not verified
legal evidence and must not be used by Legal Agent as a legal conclusion.

### Identity And Deduplication

Keep three identity levels separate:

```text
source_identity: unique parent source identity
evidence_id: unique retrieved evidence item
chunk_id: matched semantic chunk identity
```

Deduplicate final frontend sources at `source_identity` level, but preserve all
matched chunks internally for agents and trace. Internally prefer
`matched_chunks: list[MatchedChunk]`. A singular `matched_chunk` field can be
accepted as a transitional bridge and normalized into the list form.

### Matched Chunk Scoring

Target shape:

```python
{
    "id": "...",
    "chunk_type": "overview",
    "text": "...",
    "vector_distance": 0.18,
    "semantic_score": 0.82,
    "rerank_score": 0.91,
    "final_score": 0.91,
}
```

`final_score` must mean "larger is better." Do not assume a formula for
converting pgvector `vector_distance` to `semantic_score`. First verify the
current pgvector metric/operator and `hybrid_search()` contract. Only create
`semantic_score` when there is a valid conversion. Otherwise keep
`vector_distance` and use `rerank_score` or a normalized ranking score as
`final_score`.

### AgentSource Contract

Extend or normalize `AgentSource` toward this frontend-safe shape:

```python
{
    "type": "listing" | "project" | "article" | "market_metric",
    "domain": "property" | "project" | "news" | "legal" | "market",
    "id": str,
    "title": str,
    "url": str | None,
    "snippet": str | None,
    "location": dict | None,
    "citation": str | None,
    "score": float | None,
    "metadata": dict,
}
```

Rules:

- `url` is optional.
- `snippet` comes from matched chunks or normalized facts.
- `metadata` must be JSON-serializable.
- Legal sources should provide clearer citation than listing/news sources.
- The frontend should not need to inspect raw records or matched chunks.

### Structured Warning Contract

Warnings should be structured objects, not concatenated strings:

```python
{
    "code": "source_not_ready",
    "domain": "legal",
    "message": "Legal knowledge base is not ready.",
    "retryable": False,
    "details": {},
}
```

Minimum warning codes:

- `source_not_ready`
- `retrieval_error`
- `no_evidence`
- `insufficient_legal_evidence`
- `investment_market_data_missing`
- `invalid_evidence_reference`

### Market Evidence

Market evidence uses the same interface but does not require chunks:

```python
{
    "evidence_id": "ev_market_q7_apartment_price",
    "retrieval_task_id": "market_lookup_1",
    "domain": "market",
    "source_type": "market_metric",
    "source_identity": "market:q7:apartment:median_price_per_m2:2026Q2",
    "record": {...},
    "facts": {
        "metric": "median_price_per_m2",
        "value": 72000000,
        "unit": "VND/m2",
        "location": "Quan 7",
        "property_type": "apartment",
        "period": "2026-Q2",
    },
    "source": {...},
    "matched_chunks": [],
    "retrieved_for": ["investment_advisor"],
    "assigned_to": ["investment_advisor"],
    "warnings": [],
}
```

Do not force market aggregates into article evidence or fake semantic chunks.

### Agent Mapping

```text
property_search
  <- domain=property
  <- source_type=listing

legal_advisor
  <- domain=legal
  <- source_type=article
  <- category=legal
  <- must not use legal_status_claimed as legal proof

project_agent
  <- domain=project
  <- source_type=project

news_agent
  <- domain=news
  <- source_type=article
  <- category != legal

investment_advisor
  <- reuse property evidence
  <- market_metric evidence
  <- project/news evidence when the retrieval plan requires it
```

Final source mapping is based on validated `specialist_outputs.evidence_ids_used`.
Do not expose every retrieval result. Only evidence actually used by an agent or
synthesizer may become a final response source.

## Section 3: Retrieval Planner, Dependencies, And Execution

Keep `retrieval_planner_node` as one LangGraph node initially, but split its
logic into independently testable functions:

```python
build_retrieval_plan(state)
execute_retrieval_plan(plan, state)
```

### RetrievalTask

Minimum contract:

```python
{
    "task_id": str,
    "domain": str,
    "tool": str,
    "query": str,
    "filters": dict,
    "retrieved_for": list[str],
    "depends_on": list[str],
    "dependency_mode": "required" | "optional_context" | "none",
    "top_k": int,
    "rerank_top_k": int | None,
    "timeout_ms": int | None,
}
```

### RetrievalResult

Keep task execution results separate from evidence:

```python
{
    "task_id": str,
    "status": "completed" | "empty" | "failed" | "skipped",
    "evidence_ids": list[str],
    "duration_ms": int,
    "warning_ids": list[str],
    "skip_reason": str | None,
    "error": dict | None,
}
```

If a source is not ready, create a skipped task result:

```python
{
    "task_id": "search_legal_1",
    "status": "skipped",
    "skip_reason": "source_not_ready",
}
```

### Dependency Versus Assignment

Distinguish retrieval dependency from evidence assignment:

- Retrieval dependency means a task needs a previous task output to build its
  query, filters, or context.
- Evidence assignment means an agent reuses evidence already produced by another
  task without creating a new retrieval task.

Investment Agent receiving listing evidence from Property Agent is evidence
assignment, not a new dependency task.

### State Shape

Use a single evidence registry:

```python
{
    "evidence_by_id": {
        "ev_1": Evidence(...),
        "ev_2": Evidence(...),
    },
    "evidence_for_agent": {
        "property_search": ["ev_1"],
        "legal_advisor": ["ev_2"],
        "investment_advisor": ["ev_1"],
    },
    "retrieval_results": {
        "search_property_1": RetrievalResult(...),
    },
}
```

Do not copy full evidence objects into each agent bucket. Specialist agents
resolve IDs through `evidence_by_id`.

### Planning Rules

```text
property_search
  -> search_listings when listings are ready

legal_advisor
  -> search_articles(category="legal") when legal is ready

project_agent
  -> search_projects when projects are ready

news_agent
  -> search_articles(category != legal or category in news/market/guide)
     when news is ready

investment_advisor
  -> reuse property evidence when available
  -> add market_metric task when enough filters/location/property type exist
  -> add project/news tasks only when there are clear signals
```

Planner must not automatically add project/news retrieval for every investment
query. Add project/news only when:

- The query clearly mentions projects, developers, infrastructure, news, or
  market movement.
- Market/investment rules need that data.
- The source is ready.
- The supplementary retrieval can provide evidence distinct from listing search.

### Execution Levels

The first implementation may run tasks sequentially, but the contract should
support dependency levels:

```text
Level 0:
  property, legal, project, news independent retrieval

Level 1:
  tasks that truly need context from Level 0

Level 2:
  future supplementary retrieval
```

Tasks in the same level can later use `asyncio.gather`. Individual task errors
must be isolated and must not cancel the entire graph.

### Trace Semantics

Trace must distinguish:

- No task created because it was not needed.
- Task skipped because source was not ready.
- Retrieval ran but returned no results.
- Retrieval failed.

Minimum retrieval trace events:

- `retrieval_plan_created`
- `retrieval_task_started`
- `retrieval_task_completed`
- `retrieval_task_empty`
- `retrieval_task_skipped`
- `retrieval_task_failed`
- `evidence_assigned`
- `invalid_evidence_reference`

## Section 4: Specialist Outputs, Synthesis, Error Handling, And Testing

### Specialist Output Contract

Specialist agents should return explicit status:

```python
{
    "agent_name": str,
    "status": "completed" | "partial" | "no_evidence" | "failed" | "skipped",
    "content": str,
    "evidence_ids_used": list[str],
    "confidence": float | str | None,
    "warnings": list[StructuredWarning],
    "missing_evidence": list[str],
    "sources": list[AgentSource],
}
```

`sources` is transitional compatibility only. Final source mapping should come
from validated evidence IDs.

Do not treat LLM-generated confidence as calibrated probability. If the
repository has no explicit confidence scoring rule, prefer `"high"`, `"medium"`,
`"low"`, or leave confidence optional.

### Synthesis Rules

The synthesizer must not create sources from raw records and must not reference
evidence outside the registry. In the first implementation, final sources are
created only from valid `evidence_ids_used` returned by specialist outputs.

Final source mapping:

```text
specialist evidence_ids_used
  -> validate against evidence_for_agent
  -> resolve through evidence_by_id
  -> dedupe by source_identity
  -> expose frontend-safe AgentSource
  -> preserve all matched_chunks and provenance in full trace
```

Each specialist may only reference evidence that exists in `evidence_by_id` and
is assigned to that specialist in `evidence_for_agent`, or whose evidence object
contains the agent in `assigned_to`. Invalid or unassigned evidence IDs must be
dropped and recorded as structured `invalid_evidence_reference` warnings.

`findings` or `claims` linked to evidence IDs are a future extension. They are
not required for the first implementation if `content + evidence_ids_used` is
sufficient.

### Error Handling

```text
source_not_ready
  -> task skipped
  -> agent returns skipped/no_evidence/partial with clear warning

retrieval_error
  -> task failed
  -> other domains continue

empty result
  -> task status empty
  -> agent says there is no supporting evidence

invalid evidence reference
  -> source is not exposed
  -> structured trace warning is emitted

legal evidence missing
  -> Legal Agent must not make legal conclusions

investment market missing
  -> Investment Agent can discuss listing evidence if present
  -> must warn that market data is missing
```

### Negative And Anti-Hallucination Tests

- Property Agent does not create fake listings when retrieval is empty.
- Legal Agent does not conclude legal eligibility when legal evidence is absent.
- Investment Agent does not create ROI, yield, or market averages without
  evidence.
- Synthesizer does not expose invalid or unassigned evidence IDs.
- Final sources do not include evidence that was retrieved but not used.

### Unit And Integration Tests

Planner tests:

- Mixed property + legal query creates property and legal tasks.
- Investment reuses property evidence through assignment.
- Planner does not auto-add project/news for an investment query without clear
  signals.
- Source not ready produces skipped task result.

Executor tests:

- `completed`, `empty`, `failed`, and `skipped` statuses are represented.
- One task failure does not fail the whole graph.
- Evidence registry and assignment are correct.

Contract/normalization tests:

- Listing/project/article/market evidence shapes are normalized.
- `legal_status_claimed` is not treated as legal proof.
- Multiple matched chunks for one `source_identity` are preserved.

Graph integration tests:

- `run_agent_graph()` returns sources derived from valid `evidence_ids_used`.
- Invalid evidence IDs are ignored and warned.
- Legal + property mixed query returns partial answer when legal is not ready.

Backend integration tests:

- `/api/v1/chat` with Agent Service enabled returns a response compatible with
  existing frontend schema.

### Definition Of Done

Targeted tests are useful during development, but completion requires:

```powershell
pytest backend\tests -q
python -m compileall backend\app agent_service data_pipeline chatbot crawler
git diff --check
```

If source contracts or frontend types change:

```powershell
npm.cmd run lint
npm.cmd run build
```

## In Scope

- Extend `agent_service` contracts/state for retrieval plans, retrieval results,
  evidence registry, structured warnings, and used evidence IDs.
- Wire `agent_service` graph retrieval to existing `agent_service.tools.retrieval`
  and `backend.app.services.rag.hybrid_search`.
- Normalize listing, project, news, legal, and market evidence.
- Implement source readiness skip behavior and retrieval error isolation.
- Update specialist agents to consume assigned evidence and return
  `evidence_ids_used`.
- Update synthesizer to map final sources only from validated used evidence.
- Add unit and integration tests for planner, executor, contracts, graph, and
  anti-hallucination behavior.

## Out Of Scope

- New database tables or migrations.
- New crawler selectors or crawl scheduling changes.
- New market time-series infrastructure.
- Full LLM-generated claim extraction contract.
- Frontend redesign.
- Replacing the backend fallback chatbot path.

## Migration Compatibility

- Keep `AgentChatResponse` shape compatible with backend `/api/v1/chat`.
- Extend `AgentSource` rather than replacing it abruptly.
- Current `AgentSource.id` is `int | None`; the target frontend-safe source
  contract wants a string identity. During migration, either widen the existing
  field to accept `str | int | None` or expose the stable string identity through
  `metadata.source_identity` until the public schema can be safely widened.
- Keep transitional support for existing `sources` fields in specialist results
  while moving final source mapping to `evidence_ids_used`.
- Accept existing `matched_chunk` raw records from `hybrid_search()` and
  normalize internally to `matched_chunks`.
- Keep existing warning strings at the boundary only if required for old tests,
  but internally prefer structured warnings.
- Do not require frontend to read raw records or matched chunks.

## Open Implementation Notes

- Verify pgvector distance semantics before creating `semantic_score`.
- Decide whether structured warnings are Pydantic models, dataclasses, or
  TypedDicts based on the least disruptive fit with current contracts.
- Decide how much of market evidence can be backed by current aggregate helpers
  before adding future market-specific tools.
- Keep retrieval executor sequential if that reduces implementation risk, while
  preserving task dependency levels in the contract.
