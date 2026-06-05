# Real Estate Agent Platform Implementation Plan

## Current Architecture

The platform is a FastAPI + Next.js real-estate application with a production chatbot boundary split across two services:

- The frontend calls the backend only.
- The backend owns public APIs, auth, chat sessions, chat messages, user preferences, quota, and admin-facing contracts.
- The internal Agent Service owns LangGraph orchestration, Gemini routing/reasoning/synthesis, RAG retrieval tools, trace generation, async evaluation, and memory proposals.
- PostgreSQL parent tables (`listings`, `projects`, `articles`) are the public web/API source of truth.
- PostgreSQL `chunks` with BGE-M3 1024-dimensional embeddings support chatbot retrieval.
- The root-level `chatbot/` package is legacy scaffold code and is not the active production LangGraph package.

## Active Components

| Layer | Active component | Notes |
|---|---|---|
| Frontend | `frontend/` Next.js app | Calls backend API routes; must not call Agent Service directly. |
| Backend API | `backend/app/` FastAPI | Public API boundary for listings, projects, articles, auth, chat, admin, preferences, and quota. |
| Agent orchestration | `agent_service/` | Internal-only service for LangGraph, Gemini, tools, trace, eval, and memory proposals. |
| Data pipeline | `crawler/` and `data_pipeline/` | Crawls, cleans, publishes parent rows, builds chunks, and embeds text. |
| Retrieval storage | PostgreSQL + pgvector | Parent tables plus `chunks.embedding vector(1024)`. |
| Legacy scaffold | `chatbot/` | Kept for compatibility and historical tests; do not delete. |

## Chat Flow

```text
User
  |
  v
Frontend chat UI
  |
  v
Backend POST /api/v1/chat
  |
  |-- auth/session/message/quota handling
  |
  v
Internal Agent Service POST /internal/agent/chat
  |
  |-- LangGraph route
  |-- Gemini reason/synthesize
  |-- retrieve via Agent Service tools
  |-- emit trace/eval/memory proposals
  |
  v
Backend persists assistant message and metadata
  |
  v
Frontend renders backend response
```

## Data And Retrieval Flow

```text
Crawlers / legal knowledge sources
  |
  v
Clean and normalize
  |
  v
Publish parent rows: listings, projects, articles
  |
  v
Build semantic chunks
  |
  v
Embed with BGE-M3
  |
  v
Store chunks in PostgreSQL pgvector
  |
  v
Agent Service retrieval tools
```

Parent publishing is intentionally separate from chunk indexing. Web/API visibility must not be blocked by embedding or indexing failures. Agent readiness and chat traces should expose missing parent/chunk data to admins.

## Implementation Priorities

1. Keep the backend API as the only public chat contract.
2. Keep the Agent Service internal and service-authenticated.
3. Keep retrieval tools inside `agent_service`, backed by parent tables plus indexed chunks.
4. Keep parent-table publishing resilient when embeddings fail.
5. Keep memory proposals user-controlled through backend-owned preference APIs.
6. Keep admin observability focused on readiness, traces, warnings, and evaluation results.
7. Keep the root-level `chatbot/` scaffold in place, but document it as legacy.

## Verification Plan

Run these commands before merging agent-platform chatbot documentation or integration work:

```powershell
pytest backend\tests -q
python -m compileall backend\app agent_service data_pipeline chatbot crawler
cd frontend
npm.cmd run lint
npm.cmd run build
docker compose config
```

`docker compose config` requires a local `.env`. The worktree may contain an ignored `.env` copied from `.env.example` for verification; do not stage it.
