---
paths:
  - agent_service/**/*
  - backend/app/routers/chat.py
  - backend/app/services/chatbot/**/*
  - backend/app/services/agent_service/**/*
---
# RAG Multi-Agent System

## Architecture

- Framework: LangGraph (StateGraph) in `agent_service/`.
- LLM: Google Gemini 2.5 Flash via `google-genai` SDK.
- Vector store: **pgvector only** (PostgreSQL). No ChromaDB.
- Embeddings: **BAAI/bge-m3**, dimension **1024** (local HuggingFace model).
- Hybrid retrieval: pgvector kNN (`<=>`) + PostgreSQL full-text (`text_tsv` + RRF fusion).
- Reranker: Cohere `rerank-multilingual-v3.0` (optional, falls back to cosine score).

## Graph Workflow

Self-corrective agentic RAG. The compiled graph (`_new_state_graph` in
`agentic_workflow.py`) has 4 nodes with a bounded grade → rewrite retry loop:

```
supervisor (route: classify intent, select agents, rewrite query, extract filters)
  → specialist (fan-out via LangGraph Send; each runs a function-calling ReAct loop)
  → grade (heuristic, 0 LLM: reads result status + rerank score)
        ├─ ok / insufficient  → synthesize → END
        └─ retry (weak/zero results + relaxable filter, cap AGENT_MAX_CORRECTION_ROUNDS)
               → rewrite (relax SQL filters + LLM paraphrase) → re-dispatch specialists
```

- Routing (intent + agent selection + query rewrite + filters) happens inside the
  `supervisor` node's single router LLM call — there is **no** separate
  `query_understanding` node in the runtime graph.
- Specialists fan out concurrently via `Send`; concurrency is capped process-wide by
  `AGENT_MAX_CONCURRENT_LLM_CALLS` (semaphore in `llm/gemini.py`).
- `grade` is heuristic (no LLM): retries on zero-results-with-relaxable-filter or on
  weak rerank score (`AgentSource.score` < `AGENT_GRADE_MIN_SCORE`); otherwise answers,
  emitting an honest "insufficient data" message when nothing relaxable remains.
- `synthesize` validates grounding (claims' evidence ⊆ retrieved evidence) and falls
  back to deterministic concatenation on violation.

Key graph files in `agent_service/graph/`:
- `agentic_workflow.py` — graph builder + all nodes (supervisor, specialist, grade,
  rewrite, synthesize), `run_agentic_graph[_stream]`, tool registry.
- `router.py` — intent classification + agent selection + query rewrite (one LLM call).
- `state.py` — `GraphState` (incl. `correction_round`).
- `synthesis.py` — final response synthesis + grounding validation.
- `charts.py` — chart data generation for market responses.

Present but **not wired into the runtime graph** (imported only by their own tests —
treat as dead/reference code, do not assume they run): `query_understanding.py`,
`committee.py`, `memory_extraction.py`, `investment_model.py`, `blackboard.py`.

## Agents (`agent_service/agents/`)

- `base.py` — `BaseAgent`: ReAct loop, tool calling, prompt building, observability hooks.
- `fc_runner.py` — function-calling runner used by agents for tool execution.
- `orchestrator.py` — orchestrator that coordinates specialist agents.
- `property_search_agent.py` — listing search via hybrid retrieval.
- `market_analysis_agent.py` — market stats, price trends, chart generation.
- `investment_advisor_agent.py` — ROI, risk assessment, investment scoring.
- `legal_advisor_agent.py` — legal knowledge base RAG.
- `project_agent.py` — real estate project search.
- `news_agent.py` — news/article search.

## Tools (`agent_service/tools/`)

- `registry.py` — `ToolRegistry` with permission checks (per-agent `allowed_for`) and retry wrappers. One registry instance per graph run, built by `build_default_tool_registry()`.
- `retrieval.py` — hybrid search: SQL filter → pgvector kNN + full-text → rerank → resolve evidence.
- `market.py` — market data lookup tools.
- `market_stats.py` — market statistics aggregation.
- `readiness.py` — data source health/readiness checks.

## State & Checkpointing

- `GraphState` (in `agentic_workflow.py`) is the runtime state; `_agent_results` and
  `evidence_by_id` use a reset-aware merge reducer so a rewrite retry clears stale
  results. `correction_round` bounds the retry loop.
- Checkpointing is **effectively disabled**: although `AGENT_CHECKPOINT_ENABLED=true`,
  the async SQLite saver is gated behind an undefined flag and always resolves to
  `None` (it deadlocks across event loops). Streaming therefore rebuilds final state by
  merging stream updates, not from a checkpoint.
- Streaming emits SSE node events when `AGENT_STREAM_ENABLED=true`.
- `agent_service/contracts.py` defines all inter-service data models (AgentChatRequest, AgentChatResponse, Evidence, AgentSource, etc.). Note: `AgentSource.score` (not `rerank_score`) carries the rerank/relevance score that `grade` reads.

## Key Feature Flags (`agent_service/config.py`)

| Flag | Default | Effect |
|------|---------|--------|
| `AGENT_ROUTER_MODE` | `llm` | `rule` / `llm` / `hybrid` intent routing |
| `AGENT_AGENTIC_MODE` | `true` | Toggle agentic graph vs old graph |
| `AGENT_QUERY_REWRITE_ENABLED` | `true` | Query rewriting before routing |
| `AGENT_SPECIALIST_LLM_ENABLED` | `true` | LLM-powered specialist agents |
| `AGENT_BLACKBOARD_ENABLED` | `true` | Shared scratchpad between agents |
| `AGENT_STREAM_ENABLED` | `true` | SSE streaming |
| `AGENT_CHECKPOINT_ENABLED` | `true` | SQLite graph checkpointing (see note above — inert in practice) |
| `AGENT_LLM_COST_TRACKING_ENABLED` | `true` | Track estimated Gemini costs in Redis (write is off-loop, fire-and-forget) |
| `AGENT_MEMORY_FILTERS_ENABLED` | `true` | Apply user preference filters |
| `AGENT_MAX_CONCURRENT_LLM_CALLS` | `6` | Process-wide cap on concurrent Gemini calls (semaphore); lower on 429s |
| `AGENT_GRADE_MIN_SCORE` | `0.2` | `grade` retries when best `AgentSource.score` is below this |
| `AGENT_MAX_CORRECTION_ROUNDS` | `1` | Max grade→rewrite retry rounds (self-correction loop cap) |

## Backend Chat Plumbing (`backend/app/services/chatbot/`)

Distinct from the agent graph — this is orchestration on the backend side:
- `context.py` — assemble conversation context from DB history.
- `memory.py` — persist memory proposals extracted by agent.
- `quota.py` — enforce daily message limits (anon vs auth).
- `abuse_guard.py` — sliding-window rate limiting.

## Conventions

- All chatbot responses must be in Vietnamese.
- Always include sources/citations when available.
- Agent tests in `agent_service/tests/` use a fake LLM transport (no real Gemini calls).
- The backend Docker image does not install `agent_service`; use the mirrored contracts in
  `backend/app/services/agent_service/contracts.py` for backend runtime code.
