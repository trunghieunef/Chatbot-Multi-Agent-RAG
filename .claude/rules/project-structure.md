---
# Project Structure

Full-stack Vietnamese real estate chatbot platform — microservices architecture with 3 Python
services and a Next.js frontend.

## Top-Level Layout

```
shared/                     Code used by several services: config, database, models/, rag/
services/backend/           FastAPI public API (:8000)
services/agent_service/     LangGraph multi-agent RAG service (:8100, internal only)
services/pipeline_worker/   ETL job runner service (:8200, internal only)
services/frontend/          Next.js 16 App Router (:3000)
etl/crawler/                Playwright scrapers for listings, projects, news
etl/data_pipeline/          ETL modules: clean, chunk, embed, ingest
etl/airflow/                Airflow DAGs (own compose file, not in the main stack)
infra/                      Prometheus, Grafana, Alertmanager, nginx configs
scripts/                    One-off maintenance / eval scripts
data/                       Local CSV/DB assets (not fully tracked by git)
pytest.ini                  pythonpath = . (all imports start at the repo root)
```

All Python imports use full dotted paths from the repo root (`shared.models`,
`services.backend.app.routers`, `etl.data_pipeline.chunk`). No `sys.path` hacks.

## Shared (`shared/`)

- `config.py` — Pydantic Settings from the root `.env`
- `database.py` — async engine, `async_session`, `get_db` dependency, `init_db()`
- `models/` — SQLAlchemy ORM models (Listing, Project, Article, User, ChatSession, ChatMessage, Chunk, etc.)
- `rag/hybrid_search.py` — pgvector kNN + full-text RRF hybrid search
- `rag/embeddings.py` — `BGEEmbedder` (bge-m3)
- `rag/cache.py` — `JsonCache` (Redis-backed JSON cache with TTL and namespacing)

`shared/` must not import from `services/` or `etl/`.

## Backend (`services/backend/app/`)

- `main.py` — FastAPI app entry point
- `schemas/` — Pydantic v2 request/response schemas
- `routers/` — API endpoint handlers, one file per resource (`listings.py`, `market.py`, `chat.py`, `auth.py`, `projects.py`, `articles.py`, `admin.py`)
- `services/` — business logic
  - `services/agent_service/client.py` — `AgentServiceClient` (HTTP calls to agent-service)
  - `services/agent_service/contracts.py` — mirrored copy of public agent contracts (see CLAUDE.md)
  - `services/agent_service/observability.py` — persist agent traces to DB
  - `chatbot/context.py` — conversation context assembly
  - `chatbot/memory.py` — memory proposal persistence
  - `chatbot/quota.py` — daily message quota enforcement
  - `chatbot/abuse_guard.py` — sliding-window rate limiting

## Agent Service (`services/agent_service/`)

- `main.py` — FastAPI app entry point
- `contracts.py` — canonical inter-service data models
- `config.py` — Pydantic Settings, all `AGENT_*` feature flags
- `graph/` — LangGraph nodes: `agentic_workflow.py`, `router.py`, `state.py`, `blackboard.py`, `committee.py`, `synthesis.py`, `query_understanding.py`, `charts.py`, `memory_extraction.py`, `investment_model.py`
- `agents/` — specialist agents: `base.py`, `fc_runner.py`, `orchestrator.py`, `property_search_agent.py`, `market_analysis_agent.py`, `investment_advisor_agent.py`, `legal_advisor_agent.py`, `project_agent.py`, `news_agent.py`
- `tools/` — `registry.py`, `retrieval.py`, `market.py`, `market_stats.py`, `readiness.py`
- `llm/` — Gemini client, cost tracking
- `evaluation/` — LLM-as-judge scorer

## Pipeline Worker (`services/pipeline_worker/`)

- `main.py` — FastAPI app
- `runner.py` — subprocess command builder for pipeline jobs
- Routes at `/internal/pipeline/*`

## Frontend (`services/frontend/`)

- `app/` — Next.js App Router pages
- `components/` — reusable UI components
- `lib/api.ts` — all API calls centralized; base URL from `NEXT_PUBLIC_API_URL || "/api/v1"`
- `lib/types.ts` — shared TypeScript types
- `lib/utils.ts` — utilities

## Data Pipeline (`etl/data_pipeline/`)

- `clean.py`, `chunk.py`, `embed.py` — ETL stages
- `ingestors/` — one file per content type
