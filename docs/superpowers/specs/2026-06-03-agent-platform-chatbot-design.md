# Agent Platform Multi-Agent RAG Chatbot Design

## Goal

Build a feature-complete real-estate chatbot architecture before deployment. The system should become a true multi-agent RAG platform with Gemini-powered reasoning, LangGraph orchestration, multi-source retrieval, user preference memory, evaluation, admin observability, and deploy-ready service boundaries.

The design intentionally favors architecture quality over a fixed five-day deadline.

## Key Decisions

- Use an internal Agent Service rather than keeping all agent logic inside the main backend.
- Frontend calls only the main backend. It never calls the Agent Service directly.
- Backend remains the owner of auth, chat sessions, chat messages, user preferences, quota, rate limits, and public API contracts.
- Agent Service owns LangGraph orchestration, Gemini calls, RAG planning, specialist agent reasoning, trace generation, evaluation execution, and memory update proposals.
- Data Pipeline owns ingestion, chunk indexing, source readiness, and parent records for listings, projects, and articles.
- Use Gemini as the primary LLM for routing, specialist reasoning, synthesis, and LLM-as-judge evaluation.
- Keep BGE-M3 plus PostgreSQL/pgvector as the retrieval backbone.
- Use a shared PostgreSQL and Redis deployment at first for VPS simplicity, with clear schema or table prefixes for ownership.
- Deploy initially on a Google Cloud Compute Engine VM using Docker Compose.

## Architecture

```text
Frontend Next.js
  |
  | POST /api/v1/chat
  v
Backend API FastAPI
  |  - auth/session/messages/user preferences
  |  - public API contract
  |  - quota/rate limit
  |  - internal Agent Service client
  v
Agent Service FastAPI
  |  - LangGraph orchestration
  |  - Gemini router/agents/synthesizer/judge
  |  - RAG retrieval planning
  |  - trace and eval generation
  |  - memory proposals
  v
Shared Data Layer
  - PostgreSQL + pgvector
  - Redis
```

The backend stays the only public chat entrypoint. It validates auth or anonymous access, creates or loads the chat session, stores the user message, loads user preferences for authenticated users, and calls the Agent Service through an internal endpoint.

The Agent Service is an internal service. It receives curated context and user preferences from the backend, runs the LangGraph workflow, and returns the answer, sources, trace data, readiness output, and memory proposals. It does not directly mutate backend-owned user preferences.

The shared database may start as one PostgreSQL instance, but ownership must be clear. Either use PostgreSQL schemas such as `app`, `agent`, and `pipeline`, or use explicit table prefixes such as `agent_traces` and `pipeline_source_readiness`.

## Request And Response Flow

```text
ChatWidget
  -> POST /api/v1/chat
  -> backend validates auth or anonymous quota
  -> backend creates or loads ChatSession
  -> backend stores user ChatMessage
  -> backend builds selected conversation context
  -> backend loads user preferences if logged in
  -> backend calls internal Agent Service
  -> Agent Service runs LangGraph
  -> Agent Service returns answer, sources, trace summary, full trace, readiness, and memory proposals
  -> backend stores assistant ChatMessage
  -> backend stores or references trace data
  -> backend applies, rejects, or marks memory proposals pending
  -> backend returns ChatMessageResponse to frontend
```

Every chat request has a `request_id` or `correlation_id` that follows the request through frontend, backend, Agent Service, logs, traces, and evaluation records.

The backend must not send full chat history by default. It sends curated context only: relevant recent turns, session summary, selected sources from prior turns when useful, and authenticated user preferences.

Internal Agent Service request shape:

```json
{
  "request_id": "uuid",
  "message": "Mua can ho Quan 7 de dau tu duoi 5 ty",
  "session_id": "uuid",
  "user_id": 123,
  "is_authenticated": true,
  "conversation_context": [],
  "user_preferences": {},
  "requested_trace_level": "full",
  "locale": "vi-VN"
}
```

Agent Service response shape:

```json
{
  "request_id": "uuid",
  "final_response": "...",
  "agents_used": ["investment_advisor", "property_search"],
  "sources": [],
  "suggested_actions": [],
  "trace_summary": {
    "intent": "mixed",
    "agents": ["investment_advisor", "property_search"],
    "source_count": 5,
    "latency_ms": 1234,
    "warnings": []
  },
  "full_trace": {
    "routing": {},
    "steps": [],
    "retrieval": [],
    "llm_calls": [],
    "latency_ms": 1234
  },
  "memory_proposals": [
    {
      "action": "upsert",
      "key": "preferred_district",
      "value": "Quan 7",
      "confidence": 0.86,
      "evidence": "User repeatedly asks about Quan 7",
      "requires_user_confirmation": false
    }
  ],
  "readiness": {},
  "evaluation_candidate": {}
}
```

`trace_summary` is meant for the ChatWidget. `full_trace` is meant for admin/debug views. LLM-as-judge evaluation runs asynchronously after the chat response and never blocks the user response.

## LangGraph Workflow

The Agent Service uses LangGraph as the production graph engine.

```text
START
  -> Context Builder
  -> Readiness Checker
  -> Router
  -> Parallel Retrieval Planner
  -> Specialist Agents
      - Property Agent
      - Project Agent
      - Market Agent
      - News Agent
      - Legal Agent
      - Investment Agent
  -> Evidence Merger
  -> Gemini Synthesizer
  -> Safety/Groundedness Check
  -> Memory Proposal Extractor
  -> Trace Builder
  -> END
```

### Context Builder

Normalizes the request, attaches curated conversation context, session summary, user preferences, locale, and any prior source references that are useful for follow-up questions.

### Readiness Checker

Checks source readiness for listings, projects, news, legal KB, chunks, and market aggregates. Readiness behavior is hybrid:

- If a core source for an agent is missing, that agent reports the missing source clearly and avoids unsupported claims.
- If a secondary source is missing, the agent may fallback to available data with a disclaimer.

### Router

Uses Gemini structured output to select intent, target agents, retrieval needs, risk level, and relevant filters. Falls back to keyword routing when Gemini is unavailable or returns invalid output.

### Parallel Retrieval Planner

Converts routing decisions into tool calls with explicit filters. Tools include listing search, project search, news search, legal KB search, market aggregate lookup, readiness lookup, and preference lookup.

### Specialist Agents

Each specialist receives evidence and returns structured agent output. Agents may use Gemini for reasoning but must stay grounded in evidence. They should not query the database directly outside the tool/retriever interface.

### Evidence Merger

Deduplicates sources, merges evidence from multiple agents, prioritizes citation-rich sources, and flags contradictions.

### Gemini Synthesizer

Writes the final Vietnamese answer from agent results and evidence. It includes citations/source references and disclaimers where appropriate.

### Safety/Groundedness Check

Runs synchronous validation that is light enough for the chat path. This includes rule-based safety checks, required disclaimer checks, answer contract validation, and a source-required check for RAG-heavy answers. If needed, the graph may request one bounded rewrite from the synthesizer.

### Memory Proposal Extractor

Extracts user preference proposals, but does not apply them. The backend decides whether proposals are applied, rejected, or marked pending for user confirmation.

### Trace Builder

Builds both `trace_summary` for the widget and `full_trace` for admin views.

## Specialist Agents

Each agent accepts `query`, `routing`, `readiness`, `user_preferences`, and `evidence`. Each agent returns an `agent_result` with answer fragment, claims, sources, confidence, warnings, and next actions.

### Property Agent

Finds and advises on concrete listings. It uses listing chunks, structured filters, and user preferences. It can compare top listings and explain trade-offs such as price, location, area, and legal status when evidence exists.

### Project Agent

Advises on real-estate projects using project records, project chunks, and related news when available. It can discuss developer, location, status, product type, price range, and due-diligence checks. If project data is not ready, it reports readiness clearly.

### Market Agent

Analyzes the market using SQL aggregates and news evidence. It covers average price, area, price per square meter, district comparisons, and current market context. It must not fabricate time-series trends when historical data is unavailable; it should describe data as a snapshot when appropriate.

### News Agent

Summarizes and connects news articles to the user query. It provides context, but does not make investment recommendations by itself.

### Legal Agent

Provides legal guidance grounded in legal KB chunks. It always includes an appropriate disclaimer. If legal KB readiness is missing, it avoids fabricating law and returns a conservative checklist with a warning.

### Investment Agent

Combines property/project evidence, market aggregates, rent/sale data, and user risk preference. It may estimate rental yield when data is sufficient. It must clearly state that output is not official financial advice.

### Source Auditor

Checks whether important claims have sources, whether source types match the claim, and whether legal citations include enough metadata.

### Answer Synthesizer

Writes the final response from the merged evidence and agent outputs. If agents disagree, it should say so rather than choosing unsupported claims.

## Tool Interfaces

Agents must use traceable tools rather than direct ad hoc database access:

- `search_listings`
- `search_projects`
- `search_articles`
- `get_market_snapshot`
- `get_district_comparison`
- `get_source_readiness`
- `get_user_preferences`

Each tool call records retrieval events, filters, source counts, latency, and warnings into the full trace.

## Memory

Backend owns user preferences. Anonymous users only get short-lived session context and no long-term preference storage.

Preference categories:

- `location_preferences`: city, district, ward, nearby areas.
- `property_preferences`: listing type, property type, bedrooms, area range.
- `budget_preferences`: min/max price, rent/sale mode.
- `intent_preferences`: living, investing, renting, legal due diligence.
- `risk_preferences`: conservative, balanced, growth-oriented.
- `negative_preferences`: areas or property types the user dislikes.

Memory proposal shape:

```json
{
  "action": "upsert",
  "key": "preferred_district",
  "value": "Quan 7",
  "confidence": 0.86,
  "evidence": "User asked about Quan 7 in 3 recent turns",
  "requires_user_confirmation": false
}
```

Backend applies, rejects, or marks proposals as pending according to backend rules. High-confidence non-sensitive preferences can be applied automatically. Lower-confidence or user-visible preferences can be shown in ChatWidget as a confirmation hint.

## Evaluation

Evaluation has two layers.

### Golden Tests

Golden tests check stable behavior:

- correct routing for representative questions;
- retrieval returns expected source types;
- legal answers include citation and disclaimer;
- investment answers avoid guaranteed-return language;
- answer contract includes `agents_used`, `trace_summary`, and `sources`;
- readiness fallback works;
- safety rules are enforced.

### Gemini LLM-As-Judge

LLM-as-judge runs asynchronously after chat responses. It uses Gemini to score:

- `groundedness`
- `helpfulness`
- `citation_quality`
- `safety`
- `trace_completeness`

Evaluation records must store `graph_version`, `prompt_version`, and `model_name` so quality can be compared across versions. Judge failures must not affect chat responses.

## Admin Observability

The frontend gets an admin page. Backend exposes admin APIs with role checks. This admin page supports demo and product debugging, but does not replace Grafana or Prometheus for technical operations.

Admin screens:

- Chat traces: request, routing, agents, retrieval, sources, latency, warnings.
- Eval runs: judge scores, failures, reasons, model and prompt versions.
- Pipeline readiness: source counts, chunk counts, last indexed timestamps, readiness state.
- Agent health: latency, errors, timeouts, fallback count by agent.
- Top queries: common queries, no-result queries, high-cost queries.
- Feedback dashboard: thumbs up/down, issue type, comment.
- Memory proposal stats: accepted, rejected, pending, auto-applied proposals.

## Data Model Ownership

Backend-owned tables:

- `users`
- `chat_sessions`
- `chat_messages`
- `user_preferences`
- `memory_proposals`
- `chat_feedback`

Agent-owned tables:

- `agent_traces`
- `agent_trace_steps`
- `agent_llm_calls`
- `agent_retrieval_events`
- `eval_runs`
- `eval_scores`
- `agent_prompt_versions`

Pipeline-owned tables:

- `listings`
- `projects`
- `articles`
- `chunks`
- `pipeline_runs`
- `source_readiness`

The implementation may use schemas such as `app`, `agent`, and `pipeline`, or table prefixes. The important requirement is explicit ownership.

## APIs

### Backend Public APIs

- `POST /api/v1/chat`
- `GET /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{session_id}`
- `POST /api/v1/chat/feedback`
- `GET /api/v1/preferences`
- `PATCH /api/v1/preferences`
- `POST /api/v1/memory-proposals/{id}/accept`
- `POST /api/v1/memory-proposals/{id}/reject`

### Backend Admin APIs

All admin APIs require role checks:

- `GET /api/v1/admin/chat-traces`
- `GET /api/v1/admin/chat-traces/{request_id}`
- `GET /api/v1/admin/eval-runs`
- `GET /api/v1/admin/pipeline-readiness`
- `GET /api/v1/admin/agent-health`
- `GET /api/v1/admin/top-queries`
- `GET /api/v1/admin/feedback`
- `GET /api/v1/admin/memory-proposals`

### Internal Agent Service APIs

These are internal only:

- `POST /internal/agent/chat`
- `POST /internal/agent/evaluate`
- `GET /internal/agent/health`
- `GET /internal/agent/readiness`

Initial internal auth uses `X-Internal-Agent-Key`. Later deployments may move to mTLS or private network rules.

## Frontend Scope

ChatWidget improvements:

- display `trace_summary`;
- show richer source and citation cards;
- add feedback buttons;
- show memory confirmation hints;
- handle readiness/no-result messages clearly.

Admin page:

- chat trace browser;
- eval run browser;
- pipeline readiness panel;
- agent health panel;
- top query panel;
- feedback dashboard;
- memory proposal dashboard.

## Deploy Readiness

Initial Google Cloud VPS deployment uses Docker Compose:

- `frontend`
- `backend`
- `agent-service`
- `postgres` with pgvector
- `redis`
- optional `nginx` or Caddy reverse proxy
- optional `airflow` if the data pipeline runs on the same VM
- optional `prometheus` and `grafana`

Required env:

- `DATABASE_URL`
- `REDIS_URL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `GEMINI_JUDGE_MODEL`
- `HF_EMBEDDING_MODEL=BAAI/bge-m3`
- `COHERE_API_KEY` optional
- `AGENT_SERVICE_URL`
- `AGENT_INTERNAL_KEY`
- `CHATBOT_TRACE_LEVEL`
- `ANON_CHAT_DAILY_LIMIT`
- `AUTH_CHAT_DAILY_LIMIT`

Feature flags:

- `CHATBOT_AGENT_SERVICE_ENABLED`
- `CHATBOT_LLM_JUDGE_ENABLED`
- `CHATBOT_MEMORY_ENABLED`
- `CHATBOT_ADMIN_ENABLED`

Failure behavior:

- Agent Service timeout: backend returns a safe fallback and records an error trace.
- Gemini timeout: graph falls back to bounded fallback behavior.
- Retrieval no result: agent returns a no-result answer with suggested filters.
- Missing readiness: agent reports missing source or falls back with disclaimer according to hybrid readiness rules.
- Async eval failure: does not affect chat response.

## Milestones

### M1: Agent Service Foundation

Create the internal FastAPI Agent Service, internal auth, health/readiness endpoint, shared contracts, Docker Compose wiring, and backend client integration behind a feature flag.

### M2: LangGraph Production Core

Implement graph state, context builder, readiness checker, Gemini router, retrieval planner, and trace builder. The graph should run end-to-end before deep agent quality work begins.

### M3: Multi-Source RAG Tools

Standardize listing, project, news, legal, and market tools. Ensure each tool emits traceable retrieval events and consistent source metadata.

### M4: Deep Specialist Agents And Synthesizer

Implement Property, Project, Market, News, Legal, and Investment agents. Add Evidence Merger, Gemini Synthesizer, Source Auditor, and synchronous safety/groundedness validation.

### M5: Memory System

Add backend user preference tables and APIs, memory proposal storage, apply/pending/reject rules, and ChatWidget memory hints.

### M6: Evaluation System

Add golden tests, async Gemini LLM-as-judge, eval tables, prompt/model/graph version tracking, and regression commands.

### M7: Admin Observability

Add admin APIs and frontend admin pages for traces, eval runs, readiness, agent health, top queries, feedback, and memory proposal stats.

### M8: ChatWidget Upgrade

Improve the user-facing chat UI with trace summary, richer sources, feedback, memory hints, and better readiness/no-result states.

### M9: Deploy Hardening

Prepare production Docker Compose for Google Cloud VM, `.env.example`, reverse proxy notes, health checks, startup order, quota configuration, backup notes, and smoke test checklist.

### M10: Cleanup And Documentation

Update docs, mark or remove legacy root-level chatbot scaffold, document architecture, and run the full verification suite.

## Open Scope Boundaries

The first feature-complete version does not require public web search, streaming, mobile app support, cloud-managed database split, or fine-tuning. These may be added later after the Agent Platform is stable.
