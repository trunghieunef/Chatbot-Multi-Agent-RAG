# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Full-stack Vietnamese real estate platform (inspired by batdongsan.com.vn) with a multi-agent
RAG chatbot. The system is a **microservices architecture**: the public API delegates chat to a
separate internal LangGraph agent service, and ETL runs in its own pipeline-worker service.

## Architecture: three Python services + frontend

Requests flow across HTTP service boundaries:

```
Browser ──► frontend (Next.js, :3000)
              │  NEXT_PUBLIC_API_URL=/api/v1  (nginx proxies to backend in prod)
              ▼
        backend (FastAPI, :8000)              public API, auth, listings, market, chat orchestration
              │  POST /internal/agent/chat[/stream]
              │  header X-Internal-Agent-Key: $AGENT_INTERNAL_KEY
              ▼
        agent-service (FastAPI + LangGraph, :8100)   multi-agent RAG brain (internal only)

        pipeline-worker (FastAPI, :8200)      crawl/clean/chunk/embed/ingest jobs (internal only)
```

- **backend/app/** — public `/api/v1` API. The chat router (`backend/app/routers/chat.py`) handles
  auth, quota, abuse guarding, conversation context/memory, and session persistence, then calls the
  agent service via `app/services/agent_service/client.py` (`AgentServiceClient`). It does NOT
  import the agent graph. `app/services/chatbot/` is backend-side chat plumbing (context, memory,
  quota, abuse_guard) — distinct from the agent graph.
- **agent_service/** — standalone service that owns the LangGraph agentic RAG graph. Authenticated
  by the shared `X-Internal-Agent-Key`. See "Agent service internals" below.
- **pipeline_worker/** — standalone service exposing `/internal/pipeline/*` endpoints that invoke
  the `crawler/` and `data_pipeline/` modules as jobs (crawl, CSV ingest, chunk cleanup,
  maintenance).
- **frontend/** — Next.js 16 App Router, React 19, Tailwind v4. See `frontend/CLAUDE.md`.

All three Python services read the **single root `.env`** and share the same PostgreSQL/Redis.

### Agent service internals (`agent_service/`)

The graph entry point is `agent_service/graph/agentic_workflow.py`:

```
query_understanding → router (classify intent + select agents)
  → dispatch_agents (specialists run in parallel via asyncio)
  → committee/synthesis (merge results + safety review)
```

Key pieces:
- `graph/router.py` — intent classification + agent selection (`AGENT_ROUTER_MODE` = rule | llm | hybrid).
- `graph/state.py` — LangGraph state definition.
- `graph/blackboard.py` — shared scratchpad between agents.
- `graph/committee.py` — committee review of specialist answers before synthesis.
- `graph/synthesis.py` — final response synthesis.
- `graph/query_understanding.py` — query analysis and rewriting.
- `graph/charts.py` — chart data generation.
- `graph/memory_extraction.py` — extract memory proposals from responses.
- `graph/investment_model.py` — investment scoring model.
- `agents/` — specialists: `property_search_agent`, `market_analysis_agent`, `legal_advisor_agent`,
  `investment_advisor_agent`, `project_agent`, `news_agent`, plus `orchestrator.py` and `base.py`.
  Specialists can run a ReAct tool loop via `agents/fc_runner.py`.
- `tools/` — `retrieval.py` (hybrid search), `market.py`, `market_stats.py`, `readiness.py`,
  and `registry.py` (tool registry with permission checks and retry wrappers).
- `evaluation/judge.py` — LLM-as-judge scoring, exposed at `/internal/agent/evaluate`.
- State is checkpointed to SQLite (`AGENT_CHECKPOINT_PATH`, default `data/checkpoints/agent_graph.db`).
- Streaming emits SSE node events.
- Behavior is flag-driven (see `agent_service/config.py`):
  `AGENT_AGENTIC_MODE`, `AGENT_BLACKBOARD_ENABLED`, `AGENT_STREAM_ENABLED`,
  `AGENT_CHECKPOINT_ENABLED`, `AGENT_LLM_COST_TRACKING_ENABLED`,
  `AGENT_QUERY_REWRITE_ENABLED`, `AGENT_SPECIALIST_LLM_ENABLED`, etc.

### Contracts mirror (important)

`agent_service/contracts.py` is the canonical contracts file. The backend keeps a **verbatim
mirror** of the public models (AgentChatRequest, AgentChatResponse, and supporting types) in
`backend/app/services/agent_service/contracts.py` because the backend Docker image does not
install `agent_service`. **Do not import `agent_service` from backend runtime code.** Keep both
files in sync manually when public models change.

### Data / RAG pipeline

```
crawler/{sale,rent,projects,news}  ──►  data/raw/*.csv
        │
data_pipeline/clean.py → chunk.py → embed.py → ingestors/*_ingestor.py
        │
PostgreSQL: listings / projects / articles  +  chunks (polymorphic: parent_type/parent_id, embedding[1024])
        │
agent_service hybrid retrieval: SQL filter → pgvector kNN (<=>) + full-text (text_tsv RRF) → rerank → resolve
```

The **canonical embedding store is the `chunks` table** (HNSW index on `chunks.embedding`,
dimension 1024). The old `listings.embedding` column was dropped (migration `20260801_0004`).

## Current stack facts

- **Python 3.12** across all services.
- **Embeddings: `BAAI/bge-m3`, dimension 1024** (local HuggingFace model, `HF_EMBEDDING_MODEL`,
  `EMBEDDING_DIM=1024`). Runs offline by default (`CHATBOT_EMBEDDING_LOCAL_FILES_ONLY=true`).
- **LLM: Google Gemini 2.5 Flash** via `google-genai` SDK (`GEMINI_MODEL`, `GEMINI_JUDGE_MODEL`).
- **Vector store: pgvector only.** No ChromaDB anywhere in the active codebase.
- **Hybrid retrieval: pgvector kNN + PostgreSQL full-text (tsvector/RRF)**. `chunks.text_tsv` is a
  generated column with unaccent support for Vietnamese.
- Reranker: Cohere `rerank-multilingual-v3.0` (optional; falls back to cosine distance).
- **Monitoring**: Prometheus + Grafana + Alertmanager fully configured in `infra/`.
- **nginx** reverse proxy + certbot for SSL in production.

## Commands

Detailed dev commands live in `.claude/rules/development-commands.md`. Service-aware essentials:

```bash
# Infra
docker-compose up -d postgres redis            # local DB + cache
docker-compose up --build                       # full stack

# Backend (public API, :8000)
cd backend && pip install -r requirements.txt
cd backend && alembic upgrade head              # apply migrations
cd backend && uvicorn app.main:app --reload --port 8000

# Agent service (:8100) — run from repo root so `agent_service.*` imports resolve
uvicorn agent_service.main:app --reload --port 8100

# Pipeline worker (:8200)
uvicorn pipeline_worker.main:app --reload --port 8200

# Frontend (:3000)
cd frontend && npm install && npm run dev
cd frontend && npm run lint                     # ESLint (run for any frontend change)

# Data pipeline
python -m crawler.sale.crawl_urls --pages 1 5 --output data/raw/listing_urls.csv
python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/listing_details.csv --batch-size 50
```

### Tests & verification

Two pytest suites with their own `conftest.py`:

```bash
cd backend && python -m pytest tests -q          # backend API + pipeline tests
python -m pytest agent_service/tests -q           # agent graph tests (run from repo root)
python -m pytest agent_service/tests/test_router_modes.py -q          # single file
python -m pytest agent_service/tests/test_synthesis.py::test_name -q  # single test

# Python syntax/import check across active packages
python -m compileall backend/app agent_service pipeline_worker data_pipeline crawler
```

Agent tests inject an `httpx` transport / fake LLM rather than hitting a live service or Gemini —
follow that pattern when adding tests so they run offline.

## Conventions

Project rules are in `.claude/rules/*.md`. Highlights:

- **Language**: Vietnamese for UI text, LLM prompts, chatbot responses; **English** for code,
  comments, docstrings, and commit messages. URL slugs: Vietnamese without diacritics
  (`/nha-dat-ban`, `/nha-dat-cho-thue`, `/thi-truong`, `/dang-nhap`, `/dang-ky`).
- **Backend**: FastAPI async, SQLAlchemy 2.0 async (`asyncpg`), Pydantic v2 schemas in
  `app/schemas/`, all routes under `/api/v1/`, type hints required, sessions via `get_db`.
- **Migrations**: Alembic in `backend/alembic/versions/`. Never edit an existing migration — add a
  new file `YYYYMMDD_NNNN_description.py`. Check `alembic heads` after branching.
- **Frontend**: Tailwind **v4** via PostCSS plugin — **no `tailwind.config.ts`**.
  TypeScript strict, functional components, `lucide-react` icons, `recharts` charts, API calls
  in `lib/api.ts`, types in `lib/types.ts`.
- **Secrets**: everything in root `.env`; never commit real keys. `GEMINI_API_KEY` and
  `AGENT_INTERNAL_KEY` matter most.

## Two-backends warning

There are two `main.py` files under `backend/`:
- `backend/app/main.py` — the v2 FastAPI API. **Use this.**
- `backend/main.py` — legacy CSV-based backend. **Do not use.**

## Legacy / reference-only (do not build on)

`batdongsancom-crawler/`, `backend/main.py`, `data_pipeline/load_db.py`.
`RAG/` and `FrontEnd_old/` no longer exist.
`airflow/` exists but is not wired into docker-compose or active code.
