# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Full-stack Vietnamese real estate platform (inspired by batdongsan.com.vn) with a multi-agent
RAG chatbot. The system has grown into a **microservices architecture**: the public API delegates
chat to a separate internal LangGraph agent service, and ETL runs in its own worker service.

## Architecture: three Python services + frontend

The most important thing to understand is that the backend does **not** run the agent graph in-process.
Requests flow across HTTP service boundaries:

```
Browser ──► frontend (Next.js, :3000)
              │  NEXT_PUBLIC_API_URL=/api/v1  (nginx proxies to backend in prod)
              ▼
        backend (FastAPI, :8000)              public API, auth, listings, market, chat orchestration
              │  POST /internal/agent/chat[/stream]
              │  header X-Internal-Agent-Key: $AGENT_INTERNAL_KEY
              ▼
        agent-service (FastAPI + LangGraph, :8100)   the multi-agent RAG brain (internal only)

        pipeline-worker (FastAPI, :8200)      crawl/clean/chunk/embed/ingest jobs (internal only)
```

- **backend/app/** — public `/api/v1` API. The chat router (`backend/app/routers/chat.py`) handles
  auth, quota, abuse guarding, conversation context/memory, and session persistence, then calls the
  agent service via `app/services/agent_service/client.py` (`AgentServiceClient`). It does NOT import
  the agent graph. `app/services/chatbot/` is backend-side chat plumbing (context, memory, quota,
  abuse_guard, session_guard) — distinct from the agent graph.
- **agent_service/** — standalone service that owns the LangGraph agentic RAG graph. Authenticated by
  the shared `X-Internal-Agent-Key`. See "Agent service internals" below.
- **pipeline_worker/** — standalone service exposing `/internal/pipeline/*` endpoints that invoke the
  `crawler/` and `data_pipeline/` modules as jobs (crawl, CSV ingest, chunk cleanup, maintenance).
- **frontend/** — Next.js 16 App Router, React 19, Tailwind v4. See `frontend/CLAUDE.md` (which points
  to `.claude/AGENTS.md`).

All three Python services read the **single root `.env`** and share the same PostgreSQL/Redis.

### Agent service internals (`agent_service/`)

The graph entry point is `agent_service/graph/agentic_workflow.py`:

```
route (classify intent + select agents)
  → dispatch_agents (specialists run in parallel via asyncio)
  → synthesize (merge results + safety/committee review)
```

Key pieces:
- `graph/router.py` — intent classification + agent selection (`AGENT_ROUTER_MODE` = rule | llm | hybrid).
- `agents/` — specialists: property_search, market_analysis, legal_advisor, investment_advisor,
  project, news, plus `orchestrator.py` and `base.py`. Specialists can run a ReAct tool loop.
- `tools/` — `retrieval.py` (hybrid search), `market.py`/`market_stats.py`, `readiness.py`, and a
  `registry.py` tool registry.
- `graph/blackboard.py`, `committee.py`, `investment_model.py` — collaborative blackboard, committee
  review of answers, and the investment scoring model.
- `evaluation/judge.py` — LLM-as-judge scoring, exposed at `/internal/agent/evaluate`.
- State is checkpointed to SQLite (`AGENT_CHECKPOINT_PATH`, default `data/checkpoints/agent_graph.db`);
  streaming emits SSE node events. Behavior is heavily flag-driven (see `agent_service/config.py`):
  `AGENT_AGENTIC_MODE`, `AGENT_REACT_ENABLED`, `AGENT_BLACKBOARD_ENABLED`, `AGENT_STREAM_ENABLED`,
  `AGENT_CHECKPOINT_ENABLED`, `AGENT_LLM_COST_TRACKING_ENABLED`, etc.

### Data / RAG pipeline

```
crawler/{sale,rent,projects,news}  ──►  data/raw/*.csv
        │
data_pipeline/clean.py → chunk.py → embed.py → ingestors/*_ingestor.py
        │
PostgreSQL: listings / projects / articles  +  chunks (polymorphic: parent_type/parent_id, embedding)
        │
agent_service hybrid retrieval: SQL filter → pgvector kNN (<=>) → rerank → resolve
```

The **canonical embedding store is the `chunks` table** (HNSW index on `chunks.embedding`), keyed by
`parent_type` (`listing`/`project`/`article`) + `parent_id`. The old `listings.embedding` column was
dropped (migration `20260801_0004`).

## Current stack facts (override stale docs — see warning below)

- **Embeddings: `BAAI/bge-m3`, dimension 1024** (local HuggingFace model, `HF_EMBEDDING_MODEL`,
  `EMBEDDING_DIM=1024`). Runs offline by default (`CHATBOT_EMBEDDING_LOCAL_FILES_ONLY=true`).
- **LLM: Google Gemini 2.5 Flash** via `google-genai` SDK (`GEMINI_MODEL`, `GEMINI_JUDGE_MODEL`).
- **Vector store: pgvector only.** No ChromaDB.
- Reranker: Cohere `rerank-multilingual-v3.0` (optional; falls back to vector cosine distance).

## Commands

Detailed dev commands live in `.claude/rules/development-commands.md`. Service-aware essentials:

```bash
# Infra
docker-compose up -d postgres redis            # local DB + cache
docker-compose up --build                       # full stack incl. agent-service, pipeline-worker, monitoring

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

# Data pipeline (or call via pipeline-worker endpoints)
python -m crawler.sale.crawl_urls --pages 1 5 --output data/raw/listing_urls.csv
python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/listing_details.csv --batch-size 50
```

### Tests & verification

There are **two pytest suites with their own `conftest.py`** (each fixes `sys.path` for cross-package imports):

```bash
cd backend && python -m pytest tests -q          # backend API + pipeline tests
python -m pytest agent_service/tests -q           # agent graph tests (run from repo root)
python -m pytest agent_service/tests/test_router_modes.py -q          # single file
python -m pytest agent_service/tests/test_synthesis.py::test_name -q  # single test

# Python syntax/import check across the active packages
python -m compileall backend/app agent_service pipeline_worker data_pipeline crawler
```

Agent tests inject an `httpx` transport / fake LLM rather than hitting a live service or Gemini —
follow that pattern when adding tests so they run offline.

## Conventions

Project rules are split across `.claude/rules/*.md` (development-commands, environment, git-workflow,
language-convention, project-structure, security, testing, backend-coding-style, frontend-coding-style,
api-endpoints, rag-system). Highlights that affect most work:

- **Language**: Vietnamese for UI text, LLM prompts, and chatbot responses; **English** for code,
  comments, docstrings, and commit messages. URL slugs are Vietnamese without diacritics
  (`/nha-dat-ban`, `/nha-dat-cho-thue`, `/thi-truong`, `/dang-nhap`, `/dang-ky`).
- **Backend**: FastAPI async, SQLAlchemy 2.0 async (`asyncpg`), Pydantic v2 schemas in
  `app/schemas/`, all routes under `/api/v1/`, type hints required, sessions via the `get_db` dependency.
- **Migrations**: Alembic in `backend/alembic/versions/`. Never edit an existing migration — add a new
  file `YYYYMMDD_NNNN_description.py`. Multiple heads have been merged before
  (see `20260801_0011_merge_auth_and_image_heads.py`), so check `alembic heads` after branching.
- **Frontend**: Tailwind **v4** via the PostCSS plugin — there is **no `tailwind.config.ts`**.
  TypeScript strict, functional components, `lucide-react` for icons, `recharts` for charts, API calls
  centralized in `lib/api.ts`, types in `lib/types.ts`.
- **Secrets**: everything in root `.env`; never commit real keys. `GEMINI_API_KEY` and
  `AGENT_INTERNAL_KEY` matter most — without `GEMINI_API_KEY` the router/specialists fall back to
  rule/keyword mode and embeddings still work (bge-m3 is local).

## Two-backends warning

There are two `main.py` files under `backend/`:
- `backend/app/main.py` — the v2 API. **Use this.**
- `backend/main.py` — legacy CSV backend. **Do not use.**

Legacy reference-only directories (do not build on): `RAG/`, `Crawl/`, `FrontEnd_old/`,
`batdongsancom-crawler/`, `backend/main.py`, `data_pipeline/load_db.py`.

## ⚠ Docs that are partially out of date

`.claude/AGENTS.md` and several `.claude/rules/*.md` predate the microservices split and an embedding
migration. When they conflict with the code, trust the code. Specifically:
- They describe an **in-process `chatbot/` package** running the LangGraph graph. That logic now lives
  in the separate **`agent_service/`** service; there is no top-level `chatbot/` package (only
  `backend/app/services/chatbot/` plumbing).
- `.claude/rules/rag-system.md` says ChromaDB + `text-embedding-004` (1536-dim). Reality: **pgvector +
  `BAAI/bge-m3` (1024-dim)**.
- `.claude/AGENTS.md` says Gemini `gemini-embedding-001` at 768 dims. Reality: **bge-m3 at 1024 dims**;
  the `listings.embedding` column was dropped.
- The docker stack is larger than the 4-service tables suggest: it also includes `agent-service`,
  `pipeline-worker`, Prometheus/Grafana/Alertmanager + postgres/redis exporters (`infra/`), and
  nginx/certbot. Airflow lives in `airflow/` with its own `docker-compose.airflow.yml`.
