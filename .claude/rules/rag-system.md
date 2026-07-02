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

```
query_understanding
  → router (classify intent, select agents)
  → dispatch_agents (specialists run in parallel via asyncio)
  → committee (review specialist answers)
  → synthesis (merge into final response)
```

Key graph files in `agent_service/graph/`:
- `agentic_workflow.py` — entry point, `build_default_tool_registry()`, `get_agentic_registry()`
- `router.py` — intent classification + agent selection
- `query_understanding.py` — query rewriting and analysis
- `state.py` — LangGraph state definition
- `blackboard.py` — shared scratchpad between agents
- `committee.py` — committee review before synthesis
- `synthesis.py` — final response synthesis
- `charts.py` — chart data generation for market responses
- `memory_extraction.py` — extract memory proposals from responses
- `investment_model.py` — investment scoring model

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

- State checkpointed to SQLite (`AGENT_CHECKPOINT_PATH`, default `data/checkpoints/agent_graph.db`).
- Streaming emits SSE node events when `AGENT_STREAM_ENABLED=true`.
- `agent_service/contracts.py` defines all inter-service data models (AgentChatRequest, AgentChatResponse, Evidence, AgentSource, etc.).

## Key Feature Flags (`agent_service/config.py`)

| Flag | Default | Effect |
|------|---------|--------|
| `AGENT_ROUTER_MODE` | `llm` | `rule` / `llm` / `hybrid` intent routing |
| `AGENT_AGENTIC_MODE` | `true` | Toggle agentic graph vs old graph |
| `AGENT_QUERY_REWRITE_ENABLED` | `true` | Query rewriting before routing |
| `AGENT_SPECIALIST_LLM_ENABLED` | `true` | LLM-powered specialist agents |
| `AGENT_BLACKBOARD_ENABLED` | `true` | Shared scratchpad between agents |
| `AGENT_STREAM_ENABLED` | `true` | SSE streaming |
| `AGENT_CHECKPOINT_ENABLED` | `true` | SQLite graph checkpointing |
| `AGENT_LLM_COST_TRACKING_ENABLED` | `true` | Track estimated Gemini costs in Redis |
| `AGENT_MEMORY_FILTERS_ENABLED` | `true` | Apply user preference filters |

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
