# Multi-Agent Chatbot Workflow

The production chatbot uses the public backend `/api/v1/chat` endpoint as the only frontend entrypoint. The backend owns auth, chat sessions, chat messages, user preferences, quota, and public API contracts. When `CHATBOT_AGENT_SERVICE_ENABLED=true`, the backend calls the internal Agent Service at `POST /internal/agent/chat`.

The internal Agent Service owns LangGraph orchestration, Gemini routing/reasoning/synthesis, RAG retrieval planning, trace generation, async evaluation, and memory proposals. The root-level `chatbot/` package is legacy scaffold code. This plan updates documentation references but does not delete that package.

## Request Flow

```text
Frontend
  |
  v
Backend POST /api/v1/chat
  |
  |-- validate auth/session/quota
  |-- persist user ChatMessage
  |
  v
Internal Agent Service POST /internal/agent/chat
  |
  |-- route and reason with Gemini
  |-- plan retrieval against indexed chunks
  |-- run specialist tools
  |-- synthesize answer
  |-- emit trace, warnings, eval job, memory proposals
  |
  v
Backend
  |
  |-- persist assistant ChatMessage and metadata
  |-- expose stable public response contract
  |
  v
Frontend
```

The frontend never calls the Agent Service directly. It should treat backend chat responses, history, preferences, quota state, and admin-observable metadata as the public contract.

## Backend Responsibilities

The backend remains the production boundary for user-facing chat behavior:

- Public `/api/v1/chat` request and response schemas.
- Authentication and authorization.
- Chat session and chat message persistence.
- User preferences and memory proposal approval APIs.
- Quota and rate-limit enforcement.
- Admin API surfaces for agent readiness, traces, evaluation, and warnings.
- Fallback behavior when the Agent Service is disabled or unavailable.

The backend may still contain compatibility modules under `backend/app/services/chatbot/`, but those are not the active LangGraph production orchestrator. Current production orchestration belongs to `agent_service`.

## Agent Service Responsibilities

The internal Agent Service owns agentic behavior and model/tool execution:

- LangGraph graph execution.
- Gemini routing, reasoning, and response synthesis.
- Retrieval planning for property, market, legal, and investment requests.
- Tool calls over PostgreSQL parent records and indexed `chunks`.
- Trace generation for admin observability.
- Async evaluation jobs.
- Memory proposals returned to the backend for user-controlled persistence.
- Readiness warnings when parent tables or chunk indexes are missing or stale.

The Agent Service is internal-only and should be protected by service authentication. It is not a frontend API.

## Retrieval Flow

```text
User query
  |
  v
Agent Service router and retrieval planner
  |
  |-- structured filters over parent tables
  |-- semantic search over chunks
  |-- optional reranking/synthesis
  |
  v
Resolved sources and trace warnings
```

Parent tables remain the source of truth for web/API visibility:

- `listings`
- `projects`
- `articles`

The `chunks` table supports chatbot retrieval. Embedding or chunk indexing failures must not block parent rows from appearing in public web/API experiences. Missing chunks should surface as admin readiness issues and chat trace warnings.

## Data Written By Chat

For each successful chat turn, the backend persists:

- A `ChatSession` when the request does not provide an existing session.
- The user `ChatMessage`.
- The assistant `ChatMessage`.
- Structured metadata such as sources, trace identifiers, warnings, suggested actions, memory proposals, and evaluation references.

Specialist routing should be represented as structured metadata where available. Do not document the legacy `agent_used` single-string field as the source of truth for current multi-agent behavior.

## Fallback Behavior

If `CHATBOT_AGENT_SERVICE_ENABLED=false`, or the internal Agent Service is unavailable, the backend should return a safe degraded response instead of crashing the public chat endpoint. The degraded response must preserve the public response contract and should include metadata that makes the degraded path visible to admin tooling.

## Root-Level `chatbot/`

The root-level `chatbot/` package is legacy scaffold code kept for compatibility and historical tests. Documentation may mention it only as legacy scaffold. New production workflow references should point to:

- `backend/app/routers/chat.py` for the public chat API.
- `agent_service/` for LangGraph, Gemini, RAG tools, traces, evaluation, and memory proposals.
- `data_pipeline/`, `crawler/`, and database models for indexing parent records and chunks.

Do not delete the root-level `chatbot/` scaffold as part of documentation cleanup.

## Verification

Task-level verification for this workflow:

```powershell
pytest backend\tests -q
python -m compileall backend\app agent_service data_pipeline chatbot crawler
cd frontend
npm.cmd run lint
npm.cmd run build
docker compose config
```
