---
# Project Structure

Full-stack Vietnamese real estate chatbot platform — microservices architecture with 3 Python
services and a Next.js frontend.

## Top-Level Layout

```
backend/           FastAPI public API (:8000)
agent_service/     LangGraph multi-agent RAG service (:8100, internal only)
pipeline_worker/   ETL job runner service (:8200, internal only)
frontend/          Next.js 16 App Router (:3000)
data_pipeline/     ETL modules: clean, chunk, embed, ingest
crawler/           Playwright scrapers for listings, projects, news
infra/             Prometheus, Grafana, Alertmanager, nginx configs
data/              Local CSV/DB assets (not fully tracked by git)
airflow/           Airflow DAGs (exists but not wired into active stack)
batdongsancom-crawler/  Legacy crawler utilities (reference only)
```

## Backend (`backend/app/`)

- `main.py` — FastAPI app entry point. **Use `backend/app/main.py`, not `backend/main.py`.**
- `models/` — SQLAlchemy ORM models (Listing, Project, Article, User, ChatSession, ChatMessage, Chunk, etc.)
- `schemas/` — Pydantic v2 request/response schemas
- `routers/` — API endpoint handlers, one file per resource (`listings.py`, `market.py`, `chat.py`, `auth.py`, `projects.py`, `articles.py`, `admin.py`)
- `services/` — business logic
  - `agent_service/client.py` — `AgentServiceClient` (HTTP calls to agent-service)
  - `agent_service/contracts.py` — mirrored copy of public agent contracts (see CLAUDE.md)
  - `agent_service/observability.py` — persist agent traces to DB
  - `chatbot/context.py` — conversation context assembly
  - `chatbot/memory.py` — memory proposal persistence
  - `chatbot/quota.py` — daily message quota enforcement
  - `chatbot/abuse_guard.py` — sliding-window rate limiting
  - `rag/hybrid_search.py` — pgvector kNN + full-text RRF hybrid search
  - `rag/cache.py` — `JsonCache` (Redis-backed JSON cache with TTL and namespacing)
- `database.py` — async engine, `get_db` dependency, `init_db()`
- `config.py` — Pydantic Settings from `.env`

## Agent Service (`agent_service/`)

- `main.py` — FastAPI app entry point (run from repo root)
- `contracts.py` — canonical inter-service data models
- `config.py` — Pydantic Settings, all `AGENT_*` feature flags
- `graph/` — LangGraph nodes: `agentic_workflow.py`, `router.py`, `state.py`, `blackboard.py`, `committee.py`, `synthesis.py`, `query_understanding.py`, `charts.py`, `memory_extraction.py`, `investment_model.py`
- `agents/` — specialist agents: `base.py`, `fc_runner.py`, `orchestrator.py`, `property_search_agent.py`, `market_analysis_agent.py`, `investment_advisor_agent.py`, `legal_advisor_agent.py`, `project_agent.py`, `news_agent.py`
- `tools/` — `registry.py`, `retrieval.py`, `market.py`, `market_stats.py`, `readiness.py`
- `llm/` — Gemini client, cost tracking
- `evaluation/` — LLM-as-judge scorer

## Pipeline Worker (`pipeline_worker/`)

- `main.py` — FastAPI app
- `runner.py` — subprocess command builder for pipeline jobs
- Routes at `/internal/pipeline/*`

## Frontend (`frontend/`)

- `app/` — Next.js App Router pages
- `components/` — reusable UI components
- `lib/api.ts` — all API calls centralized; base URL from `NEXT_PUBLIC_API_URL || "/api/v1"`
- `lib/types.ts` — shared TypeScript types
- `lib/utils.ts` — utilities

## Data Pipeline (`data_pipeline/`)

- `clean.py`, `chunk.py`, `embed.py` — ETL stages
- `ingestors/` — one file per content type
- `load_db.py` — legacy loader, do not use

## Two Backends Warning

| File | Status |
|------|--------|
| `backend/app/main.py` | **Active v2 API — use this** |
| `backend/main.py` | Legacy CSV backend — **do not use** |

## Legacy / Do Not Build On

- `backend/main.py` — legacy
- `data_pipeline/load_db.py` — legacy
- `batdongsancom-crawler/` — reference only
- `airflow/` — not wired into active stack
