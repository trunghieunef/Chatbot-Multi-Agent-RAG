# Agent Platform Public MVP Hardening Design

## Goal

Make the current Agent Platform safe enough for a public MVP while preserving the
existing architecture and avoiding conflicts with unrelated listing, crawler, and
report changes already present in the working tree.

This spec focuses on security, quota enforcement, observability persistence,
controlled evaluation, admin visibility, and resilience. It does not change the
agent reasoning model or retrieval ranking strategy.

## Current Context

The public chat entrypoint is the backend `/api/v1/chat` router. The backend
owns public API contracts, authentication, chat sessions, messages, memory
proposal persistence, feedback, and admin APIs. When
`CHATBOT_AGENT_SERVICE_ENABLED=true`, the backend calls the internal Agent
Service through `AgentServiceClient`.

The Agent Service owns the LangGraph workflow and returns:

- `trace_summary`
- `full_trace.steps`
- `full_trace.retrieval_plan`
- `full_trace.retrieval_results`
- `full_trace.evidence`
- `full_trace.evidence_for_agent`
- `agent_results`
- `readiness`
- `evaluation_candidate`

The database already has observability tables:

- `agent_traces`
- `agent_trace_steps`
- `agent_llm_calls`
- `agent_retrieval_events`
- `eval_runs`
- `eval_scores`

At the moment, the backend mostly persists a single `AgentTrace` row with
summary JSON. Step, retrieval, and eval rows are not fully populated.

## Non Goals

- Do not implement LLM-based routing or LLM specialist reasoning in this spec.
- Do not refactor `agent_service` package boundaries.
- Do not rewrite hybrid search, chunking, crawling, or listing image behavior.
- Do not change public response shapes in a breaking way.
- Do not require Kubernetes, Helm, or a separate tracing backend.
- Do not modify dirty listing, crawler, frontend listing, or report files unless
  a later implementation plan explicitly scopes them in.

## Design Principles

1. Public safety before agent intelligence.
2. Prefer additive changes over contract-breaking changes.
3. Use existing models, routers, and settings where possible.
4. Keep chat response latency bounded. Evaluation and expensive observability
   work must not block user-visible chat when avoidable.
5. Every new behavior must be testable without a live Gemini, Cohere, Redis, or
   Postgres service where practical.
6. Store enough trace data to debug production issues without logging secrets or
   excessive user text.

## Scope

### 1. Chat Session Ownership

Problem:

`GET /chat/sessions/{session_id}` currently loads a session by UUID and returns
its messages without checking the current user. This is inconsistent with
`send_message`, which rejects access to another user's session.

Design:

- Add `user: User | None = Depends(get_optional_user)` to
  `get_session_history`.
- Reuse the ownership rule from `send_message`:
  - If `session.user_id is not None`, then `user` must exist and
    `session.user_id == user.id`.
  - Otherwise return 404.
- Anonymous sessions remain readable only if they are not tied to a user. This
  preserves current anonymous behavior while fixing authenticated session
  leakage.
- Return 404 instead of 403 to avoid confirming that a session exists.

Tests:

- Anonymous user cannot read authenticated user's session.
- Authenticated user cannot read another authenticated user's session.
- Owner can read their session.
- Anonymous session remains readable by direct session ID under the current
  public contract.

Open point intentionally fixed by design:

Anonymous session IDs remain bearer secrets. A future auth/session-cookie design
can tighten that, but this spec avoids a larger frontend session migration.

### 2. Chat Quota Enforcement

Problem:

Settings define `ANON_CHAT_DAILY_LIMIT` and `AUTH_CHAT_DAILY_LIMIT`, but the
chat route does not visibly enforce them.

Design:

- Add a backend-owned quota helper under `backend/app/services/chatbot/quota.py`.
- Quota should count chat messages by day using existing `ChatMessage` and
  `ChatSession` tables.
- Authenticated quota:
  - Count user messages for sessions where `ChatSession.user_id == user.id`.
  - Window: current UTC calendar day.
  - Limit: `AUTH_CHAT_DAILY_LIMIT`.
- Anonymous quota:
  - Prefer a stable anonymous session id when `body.session_id` is present.
  - For new anonymous sessions, perform a conservative check after session
    creation and before agent execution.
  - Count user messages for anonymous sessions only when session id is known.
  - Limit: `ANON_CHAT_DAILY_LIMIT`.
- If the quota is exceeded, return HTTP 429 with a safe message and do not call
  the Agent Service.
- Keep the first implementation database-backed. Redis quota can be added later
  if needed.

Why not IP-based quota now:

The current router does not consistently model client IP or trusted proxy
headers. IP quota is easy to get wrong behind reverse proxies. This spec keeps
the implementation deterministic and testable.

Tests:

- Authenticated user at limit gets 429.
- Authenticated user below limit reaches the agent pipeline.
- Anonymous existing session at limit gets 429.
- Quota rejection does not persist a user message or assistant message.
- Quota counts only `role="user"` messages.

### 3. Observability Persistence

Problem:

`AgentTrace` stores high-level summary and full trace JSON, but the normalized
observability tables are not fully used.

Design:

Extend `persist_agent_observability` or split it into a small module:

`backend/app/services/agent_service/observability.py`

Responsibilities:

- Persist the existing `AgentTrace` summary row.
- Persist one `AgentTraceStep` per entry in `response.full_trace["steps"]`.
- Persist one `AgentRetrievalEvent` per retrieval event found in:
  - `response.full_trace["steps"][retrieval_planner].output.retrieval_events`
  - or `response.full_trace["retrieval_results"]` if event details are missing.
- Persist status as `success`, `partial`, or `error` using response warnings and
  fallback modes.
- Avoid duplicate writes for the same `request_id` in normal operation.

Step mapping:

- `step_name`: `step["step_name"]`
- `status`: `step["status"]`, default `success`
- `latency_ms`: `step["latency_ms"]`, default 0
- `input_json`: `{}` for now, unless the step already includes explicit safe
  input data
- `output_json`: `step["output"]`, with size guard
- `error_message`: `step.get("error_message")`

Retrieval event mapping:

- `request_id`: response request id
- `tool_name`: event tool name when available, otherwise task tool name
- `parent_type`: listing, project, article, or market when available
- `filters_json`: filters from the retrieval task or event
- `result_count`: result count or number of evidence ids
- `latency_ms`: task duration when available
- `status`: completed, empty, failed, skipped, or success
- `metadata_json`: task id, domain, warning codes, skip reason

Size guard:

- Large `output_json` fields should be truncated or summarized before row-level
  storage.
- Full trace JSON remains in `AgentTrace.full_trace_json` for detailed admin
  debugging.

Tests:

- Chat response with two trace steps creates two `AgentTraceStep` rows.
- Retrieval results create `AgentRetrievalEvent` rows.
- Legacy fallback trace still creates one `AgentTrace` row and no invalid step
  rows.
- Duplicate request id does not crash the chat route in retry scenarios.

### 4. Controlled Async Evaluation

Problem:

The Agent Service exposes `/internal/agent/evaluate`, and the judge can score
answers, but chat requests do not trigger evaluation in a controlled way.

Design:

Add backend settings:

- `CHATBOT_EVAL_ENABLED: bool = False`
- `CHATBOT_EVAL_SAMPLE_RATE: float = 0.0`
- `CHATBOT_EVAL_SYNC_FOR_TESTS: bool = False`

Behavior:

- After a successful agent response is persisted, decide whether to enqueue an
  eval run.
- Create an `EvalRun` row with status `pending`.
- If enabled and sampled, call Agent Service evaluate in a background task.
- On completion, update `EvalRun.status` to `completed` and create `EvalScore`
  rows.
- On failure, update `EvalRun.status` to `failed` and store a safe error.
- Do not block the user response unless `CHATBOT_EVAL_SYNC_FOR_TESTS=true`.

Sampling:

- If sample rate is 0.0, no automatic eval.
- If sample rate is 1.0, evaluate every eligible response.
- Use deterministic sampling in tests by injecting a sampler or monkeypatching
  the decision helper.

Eligibility:

- Evaluate only non-empty assistant responses.
- Skip known fallback modes if desired:
  - `agent_service_error`
  - `legacy_pipeline`
- Keep this decision in one helper so it can change safely.

Tests:

- Eval disabled creates no `EvalRun`.
- Eval enabled but not sampled creates no `EvalRun`.
- Eval sampled creates pending and then completed/failed rows.
- Evaluation failure does not fail `send_message`.
- Agent Service evaluate request includes question, answer, sources, trace,
  graph version, prompt version, and model name when available.

### 5. Admin API Improvements

Problem:

Admin APIs exist, but `top_queries` is currently a stub and trace details do not
fully expose normalized observability data.

Design:

Add or extend admin endpoints without breaking existing routes:

- `GET /admin/chat-traces`
  - Existing route remains.
  - Add optional query params: `status`, `intent`, `limit`.
- `GET /admin/chat-traces/{request_id}`
  - Include summary trace plus related steps, retrieval events, and eval runs.
- `GET /admin/top-queries`
  - Return aggregated recent user messages by normalized text or session title.
  - If exact query extraction is not yet available, aggregate from chat messages
    joined to sessions and limit to recent rows.
- `GET /admin/agent-health`
  - Keep existing grouped status.
  - Optionally include avg latency and recent error count.

Security:

- All admin routes continue to depend on `require_admin_user`.
- Non-admin users receive 403.

Tests:

- Every admin route depends on `require_admin_user`.
- Top queries returns real items from fake DB rows.
- Trace detail includes steps/retrieval/eval when present.

### 6. Agent Service Client Resilience

Problem:

The backend client has a timeout and safe errors, but no retry policy or
structured failure categories.

Design:

- Keep default timeout as configured by `AGENT_SERVICE_TIMEOUT_SECONDS`.
- Add at most one retry for transient network errors:
  - connect timeout
  - read timeout
  - connect error
- Do not retry HTTP 4xx.
- Do not retry request validation errors.
- Keep error messages safe and short.
- Include an internal error type on `AgentServiceError`, such as:
  - `timeout`
  - `network`
  - `http_status`
  - `invalid_response`

Tests:

- Timeout is wrapped as `AgentServiceError` with type `timeout`.
- 500 response is not retried more than configured.
- 401 response is not retried.
- One transient network failure followed by success returns success.

### 7. Frontend Compatibility

Public chat response shape should remain compatible with current frontend types.

Allowed additive fields:

- trace detail links for admin views
- eval summary in admin views

Avoid:

- Renaming `agent_used`
- Removing `agents_used`
- Changing source shape
- Requiring frontend changes for normal chat to keep working

Admin frontend can be updated later in implementation if the backend exposes
new detail data, but this spec does not require a visual redesign.

## Data Flow

1. User calls `POST /api/v1/chat`.
2. Backend resolves or creates session.
3. Backend checks session ownership.
4. Backend checks quota.
5. Backend builds conversation context and user preferences.
6. Backend calls Agent Service or legacy fallback.
7. Backend persists user message and assistant message.
8. Backend persists `AgentTrace`, trace steps, retrieval events.
9. Backend stores memory proposals.
10. Backend optionally schedules eval.
11. Backend returns the chat response.

Important ordering:

- Quota must run before agent execution.
- Observability persistence should not prevent the assistant response unless the
  database transaction itself is already failing.
- Evaluation must not block normal response.

## Error Handling

- Unauthorized session access returns 404.
- Quota exceeded returns 429.
- Agent Service failure returns the existing safe fallback response.
- Observability row persistence errors should be logged and reflected in
  `AgentTrace.status` when possible, but should not hide a valid answer.
- Evaluation errors update eval status and do not affect chat response.

## Testing Strategy

Focused test files:

- `backend/tests/test_chat_agent_service_integration.py`
- `backend/tests/test_admin_observability.py`
- `backend/tests/test_agent_service_client.py`
- New `backend/tests/test_chat_quota.py`
- New `backend/tests/test_agent_observability_persistence.py`
- New `backend/tests/test_agent_eval_trigger.py`

Verification commands for implementation:

```powershell
python -m pytest backend\tests\test_chat_agent_service_integration.py backend\tests\test_admin_observability.py backend\tests\test_agent_service_client.py backend\tests\test_chat_quota.py backend\tests\test_agent_observability_persistence.py backend\tests\test_agent_eval_trigger.py -q
python -m compileall backend\app agent_service
```

Full regression should be run before merge:

```powershell
python -m pytest backend\tests -q
python -m compileall backend\app agent_service pipeline_worker
docker compose config --services
```

## Conflict Avoidance

Implementation should touch only these likely areas:

- `backend/app/routers/chat.py`
- `backend/app/routers/admin.py`
- `backend/app/config.py`
- `backend/app/services/agent_service/client.py`
- `backend/app/services/agent_service/observability.py`
- `backend/app/services/chatbot/quota.py`
- `backend/app/models/agent_observability.py` only if a small model helper is
  needed; avoid migration unless a column is truly missing
- Backend tests listed above
- Optional admin frontend files only if backend response changes require it

Do not touch:

- `backend/app/routers/listings.py`
- `backend/app/schemas/listing.py`
- `backend/app/models/listing_image.py`
- `crawler/`
- `data_pipeline/ingestors/listings_ingestor.py`
- `frontend/components/listing/`
- `report/`

## Rollout Plan

1. Ship session ownership fix and quota first.
2. Ship observability persistence next.
3. Ship controlled eval trigger behind disabled-by-default config.
4. Ship admin API improvements.
5. Ship client retry/error categorization.

Feature flags:

- Keep evaluation disabled by default.
- Keep Agent Service fallback behavior unchanged.
- No changes to `CHATBOT_AGENT_SERVICE_ENABLED` default in this spec.

## Acceptance Criteria

- Authenticated chat history cannot be read by another user or anonymous user.
- Quota settings are enforced with HTTP 429.
- Agent trace detail can be inspected through admin APIs.
- Trace steps and retrieval events are stored as normalized rows.
- Eval can be enabled by config and runs without blocking chat.
- Agent Service outages still return safe fallback responses.
- Existing agent platform tests continue to pass.

## Risks

- Counting anonymous quota by session id is weaker than IP/device-level quota.
  This is accepted for the first public MVP to avoid unreliable proxy handling.
- Persisting full trace details may increase database size. Row-level output
  should be summarized where needed.
- Background eval requires careful DB session handling. Tests should cover both
  sync-for-tests and background behavior.
