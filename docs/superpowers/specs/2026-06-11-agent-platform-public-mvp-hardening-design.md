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

Implementation note:

Extract the ownership check into a shared helper so both `send_message` and
`get_session_history` reuse the same logic:

```python
# backend/app/services/chatbot/session_guard.py
async def verify_session_ownership(
    session: ChatSession,
    user: User | None,
) -> None:
    """Raise 404 if session belongs to a different user."""
    if session.user_id is not None:
        if user is None or session.user_id != user.id:
            raise HTTPException(status_code=404, detail="Session not found")
```

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

### 3. Free-Tier Chat Abuse Guard

Problem:

Chat daily quota prevents a user from sending too many messages over a day, but
does not protect against rapid bursts (brute-force, scripted abuse, or
accidental spam). Because LLM-enabled modes may use Google Gemini free-tier or
low-tier quota, a malicious or buggy client could burn through external API
quota quickly and make the chatbot unavailable for everyone else.

Design:

Add a lightweight abuse guard in front of the chat endpoint, separate from the
daily quota system. This is not a full anti-DDoS system; it only prevents rapid
chat bursts from consuming local resources and external LLM quota.

`backend/app/services/chatbot/abuse_guard.py`

Settings (new):

- `CHAT_ABUSE_GUARD_ENABLED: bool = True`
- `CHAT_ABUSE_GUARD_ANON_MAX_REQUESTS: int = 10`
- `CHAT_ABUSE_GUARD_ANON_WINDOW_SECONDS: int = 60`
- `CHAT_ABUSE_GUARD_AUTH_MAX_REQUESTS: int = 30`
- `CHAT_ABUSE_GUARD_AUTH_WINDOW_SECONDS: int = 60`

Behavior:

- Use an in-memory sliding-window counter (collections.deque or similar) as the
  first implementation. Do not require Redis for the MVP guard.
- Authenticated users: key by `user.id`. Anonymous users: key by
  `body.session_id` when the request already carries one; otherwise fall back
  to client IP from `request.client.host`. **Do not** key by a session that
  was just created during this request — a spammer could bypass the limit by
  sending requests without `session_id`, each creating a fresh session.
- If the abuse guard threshold is exceeded, return HTTP 429 with `Retry-After`
  header and a safe Vietnamese message.
- The abuse guard runs BEFORE quota check and agent execution. Abuse guard and
  daily quota are independent checks.
- The abuse guard must be a FastAPI dependency so it can be tested in isolation.

Why in-memory first:

- Avoids Redis dependency for MVP.
- Acceptable trade-off: guard counters reset on server restart, which is tolerable
  for the first public release.
- Can be upgraded to Redis-backed sliding window later without changing the
  dependency interface.

Tests:

- Authenticated user above guard threshold gets 429 with Retry-After header.
- Authenticated user below guard threshold proceeds to quota check.
- Anonymous user without session_id is guarded by IP.
- Guard counter resets after window passes.
- Guarded request does not count toward daily quota.
- Abuse guard dependency works in isolation with FastAPI TestClient.

### 4. Observability Persistence

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
- `input_json`: capture normalized query text for `context_builder` and
  `router` steps (query text is not a secret and is essential for debugging).
  For other steps, keep `{}` unless the step already includes explicit safe
  input data.
- `output_json`: `step["output"]`, truncated at **16 KB** (16 384 characters).
  Full output remains in `AgentTrace.full_trace_json` for admin debugging.
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

- `output_json` truncated at 16 KB per row.
- `input_json` truncated at 4 KB per row.
- Full trace JSON remains in `AgentTrace.full_trace_json` for detailed admin
  debugging.

Idempotency:

- Use **app-level replace-by-request-id**, not new DB unique constraints. This
  avoids a migration and keeps the implementation aligned with the current
  observability models.
- `AgentTrace.request_id` is already unique in the current model. For the
  summary row, first query by `request_id`; update the existing `AgentTrace`
  when found, otherwise insert a new row. Do not blindly `db.add(AgentTrace(...))`
  for a replayed request.
- Before inserting `AgentTraceStep` rows for a `request_id`, `DELETE` existing
  `agent_trace_steps` rows with that `request_id`, then `INSERT` the new set.
- Before inserting `AgentRetrievalEvent` rows for a `request_id`, `DELETE`
  existing `agent_retrieval_events` rows with that `request_id`, then `INSERT`
  the new set.
- This correctly handles multiple retrieval events with the same `tool_name`
  (e.g. `search_articles` for both legal and news domains, or separate
  `retrieval_task_started` + `retrieval_task_completed` events).
- Duplicate `request_id` must not crash the chat route and must not create
  duplicate rows.

Trace data retention:

- Chat trace data accumulates quickly. At ~10 rows per chat request and 1 000
  chats/day, the system produces ~300 000 rows/month.
- Add a background cleanup job (or a simple scheduled task) that deletes:
  - Anonymous trace rows older than 30 days.
  - Authenticated trace rows older than 90 days.
- The cleanup runs outside the chat request path and must not block chat.
- Keep this configurable via settings:
  - `OBSERVABILITY_ANON_RETENTION_DAYS: int = 30`
  - `OBSERVABILITY_AUTH_RETENTION_DAYS: int = 90`
  - `OBSERVABILITY_CLEANUP_ENABLED: bool = True`

Tests:

- Chat response with two trace steps creates two `AgentTraceStep` rows.
- Retrieval results create `AgentRetrievalEvent` rows.
- Legacy fallback trace still creates one `AgentTrace` row and no invalid step
  rows.
- Duplicate request id does not crash the chat route in retry scenarios.
- Idempotent replace-by-request-id updates the `AgentTrace` summary row and
  does not create duplicate step or retrieval rows.
- Retention cleanup deletes old anonymous rows and keeps recent authenticated
  rows.

### 5. Controlled Async Evaluation

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
  **Important**: the background task must open its own `async_session()` —
  it must never use the request-scoped `db` dependency, because that session
  is closed after the HTTP response is sent.
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

Stale eval detection:

- Background tasks can be lost (server restart, crash, task queue overflow).
  An `EvalRun` stuck in `pending` status will remain pending forever.
- Add a lightweight scheduled check that runs every 5 minutes:
  - Query `EvalRun` rows where `status = 'pending'` and `created_at < now() -
    interval '10 minutes'`.
  - Mark them as `status = 'failed'` with `error_message = 'eval_timeout_stale'`.
- This can be a simple loop in the FastAPI lifespan background task, not a
  separate service.
- For the MVP, this is a best-effort cleanup; it does not need to be perfectly
  reliable.

Tests:

- Pending eval older than 10 minutes is marked failed by cleanup.
- Recent pending eval is not touched.
- Cleanup does not affect already-completed eval rows.

### 6. Admin API Improvements

Problem:

Admin APIs exist, but `top_queries` is currently a stub and trace details do not
fully expose normalized observability data.

Design:

Add or extend admin endpoints without breaking existing routes:

- `GET /admin/chat-traces`
  - Existing route **and response shape** remain unchanged (returns a flat
    list). Do not change the response structure to avoid breaking the admin
    frontend.
  - Add query params: `status`, `intent`, `limit` (default 50, max 200),
    `offset` (default 0).
- `GET /admin/chat-traces/search` **(new endpoint)**
  - Returns a paginated object: `{"items": [...], "total": int}`.
  - Accepts the same query params as `/chat-traces` plus `q` for free-text
    search across trace data.
  - This keeps the existing endpoint backward-compatible while adding
    pagination capability.
  - Declare this route before `GET /admin/chat-traces/{request_id}` so FastAPI
    does not parse `"search"` as a `request_id`.
- `GET /admin/chat-traces/{request_id}`
  - Include summary trace plus related steps, retrieval events, and eval runs.
- `GET /admin/top-queries`
  - Return aggregated recent user messages by normalized text or session title.
  - Query params: `since` (ISO datetime, default 24h ago), `until` (ISO
    datetime, default now), `limit` (default 20, max 100).
  - If exact query extraction is not yet available, aggregate from chat messages
    joined to sessions and limit to recent rows.
- `GET /admin/agent-health`
  - Keep existing grouped status.
  - Include avg latency (last 100 requests) and error count (last 1 hour).

Security:

- All admin routes continue to depend on `require_admin_user`.
- Non-admin users receive 403.

Tests:

- Every admin route depends on `require_admin_user`.
- Top queries returns real items from fake DB rows.
- Trace detail includes steps/retrieval/eval when present.
- Route order keeps `/admin/chat-traces/search` from being captured by
  `/admin/chat-traces/{request_id}`.

### 7. Agent Service Client Resilience

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

### 8. Frontend Compatibility

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
2. If `body.session_id` is present:
   - Load existing session and check session ownership.
   - Run the abuse guard keyed by `user.id` for authenticated users, or
     `body.session_id` for anonymous users.
3. If `body.session_id` is **not** present:
   - If authenticated, run the abuse guard by `user.id` before creating a new
     session, then create a session with `user_id=user.id`.
   - If anonymous, run the abuse guard by client IP before creating a new
     anonymous session.
4. Backend checks daily quota.
5. Backend builds conversation context and user preferences.
6. Backend calls Agent Service or legacy fallback.
7. Backend persists user message and assistant message.
8. Backend persists `AgentTrace`, trace steps, retrieval events.
9. Backend stores memory proposals.
10. Backend optionally schedules eval.
11. Backend returns the chat response.

Important ordering:

- Abuse guard must run before quota check, session creation for no-session
  requests, and agent execution.
- Quota must run before agent execution.
- User/assistant chat messages must be persisted and **explicitly committed**
  before observability rows are written. Strategy:
  - Chat messages (`ChatMessage` user + assistant) are written in the request's
    primary DB session and committed via `await db.commit()`.
  - After that commit succeeds, observability rows (`AgentTrace`,
    `AgentTraceStep`, `AgentRetrievalEvent`) are written in a **separate**
    DB session (`async_session()` opened by the observability helper).
  - This ensures a trace write failure cannot roll back chat messages, and
    session/user foreign key references are visible because the `AgentTrace`
    row is inserted only after the chat transaction is durably committed.
- Observability persistence is **best-effort**: if the separate session fails,
  log the error and continue because the user already has their answer.
- Evaluation must not block normal response.

## Error Handling

- Unauthorized session access returns 404.
- Abuse guard threshold exceeded returns 429 with `Retry-After` header.
- Quota exceeded returns 429.
- Agent Service failure returns the existing safe fallback response.
- Observability row persistence errors should be logged and reflected in
  `AgentTrace.status` when possible, but should not hide a valid answer.
  Observability writes must use a separate DB session from chat message
  writes so that a trace failure cannot roll back the user's message.
- Evaluation errors update eval status and do not affect chat response.

## Testing Strategy

Focused test files:

- `backend/tests/test_chat_agent_service_integration.py`
- `backend/tests/test_admin_observability.py`
- `backend/tests/test_agent_service_client.py`
- New `backend/tests/test_chat_quota.py`
- New `backend/tests/test_chat_abuse_guard.py`
- New `backend/tests/test_agent_observability_persistence.py`
- New `backend/tests/test_agent_eval_trigger.py`

Verification commands for implementation:

```powershell
python -m pytest backend\tests\test_chat_agent_service_integration.py backend\tests\test_admin_observability.py backend\tests\test_agent_service_client.py backend\tests\test_chat_quota.py backend\tests\test_chat_abuse_guard.py backend\tests\test_agent_observability_persistence.py backend\tests\test_agent_eval_trigger.py -q
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
- `backend/app/schemas/admin.py` only for additive admin trace detail fields
- `backend/app/main.py` only if lifespan hooks are needed for cleanup tasks
- `backend/app/config.py`
- `backend/app/services/agent_service/client.py`
- `backend/app/services/agent_service/observability.py`
- `backend/app/services/chatbot/quota.py`
- `backend/app/services/chatbot/abuse_guard.py`
- `backend/app/services/chatbot/session_guard.py`
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

1. Ship session ownership fix, quota enforcement, and abuse guard first.
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
- Abuse guard settings are enforced with HTTP 429 and Retry-After header.
- Quota settings are enforced with HTTP 429.
- Agent trace detail can be inspected through admin APIs.
- Trace summary, steps, and retrieval events are stored with idempotent
  replace-by-request-id behavior.
- Old trace data is cleaned up per retention policy.
- Eval can be enabled by config and runs without blocking chat.
- Stale pending eval runs are detected and marked failed.
- Agent Service outages still return safe fallback responses.
- Existing agent platform tests continue to pass.

## Risks

- Abuse guard by IP for anonymous users without session_id can be unreliable
  behind reverse proxies (shared IPs, IPv6 prefixes). This is accepted for the
  first MVP; a future iteration can use more robust fingerprinting.
- Counting anonymous quota by session id is weaker than IP/device-level quota.
  This is accepted for the first public MVP to avoid unreliable proxy handling.
- In-memory abuse guard counters reset on server restart. Acceptable for MVP; upgrade
  path to Redis is documented.
- Persisting full trace details may increase database size. Row-level output
  is truncated at 16 KB and old rows are cleaned up per retention policy.
- Background eval requires careful DB session handling. Tests should cover both
  sync-for-tests and background behavior.
- Stale eval cleanup runs in the same process; if the server is down, cleanup
  pauses until restart. This is acceptable for MVP.
