# Agent Platform Public MVP Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public chat agent platform safe for an MVP by adding session ownership checks, quota and abuse protection, normalized observability, controlled eval, admin visibility, and client resilience.

**Architecture:** Keep the public API in `backend/app/routers/chat.py` and move reusable behavior into small helpers under `backend/app/services/chatbot/` and `backend/app/services/agent_service/`. Observability writes run after chat message commit in a separate DB session so trace failures cannot roll back user-visible chat. Admin APIs stay backward-compatible by preserving the existing flat `/admin/chat-traces` response and adding a new paginated `/admin/chat-traces/search` endpoint.

**Tech Stack:** FastAPI, SQLAlchemy async sessions, Pydantic schemas, pytest, httpx, existing Agent Service contracts.

---

## File Structure

- Create `backend/app/services/chatbot/session_guard.py`: shared ownership check for `ChatSession`.
- Create `backend/app/services/chatbot/quota.py`: database-backed daily chat quota helper.
- Create `backend/app/services/chatbot/abuse_guard.py`: in-memory sliding-window guard for burst control.
- Create `backend/app/services/agent_service/observability.py`: idempotent `AgentTrace`, `AgentTraceStep`, and `AgentRetrievalEvent` persistence plus retention cleanup.
- Modify `backend/app/routers/chat.py`: integrate ownership helper, abuse guard, quota, committed chat-message flow, observability helper, and eval scheduling.
- Modify `backend/app/config.py`: add chat quota, abuse guard, observability retention, and eval settings.
- Modify `backend/app/main.py`: optional lifespan task for stale eval cleanup and trace retention cleanup.
- Modify `backend/app/routers/admin.py`: add search endpoint, detail joins, top queries, and health metrics.
- Modify `backend/app/schemas/admin.py`: add additive trace detail fields.
- Modify `backend/app/services/agent_service/client.py`: add retry and typed errors.
- Test files:
  - `backend/tests/test_chat_agent_service_integration.py`
  - `backend/tests/test_admin_observability.py`
  - `backend/tests/test_agent_service_client.py`
  - `backend/tests/test_chat_quota.py`
  - `backend/tests/test_chat_abuse_guard.py`
  - `backend/tests/test_agent_observability_persistence.py`
  - `backend/tests/test_agent_eval_trigger.py`

Do not edit listing, crawler, data pipeline ingestor, frontend listing, or report files.

---

### Task 1: Session Ownership Guard

**Files:**
- Create: `backend/app/services/chatbot/session_guard.py`
- Modify: `backend/app/routers/chat.py`
- Test: `backend/tests/test_chat_agent_service_integration.py`

- [ ] **Step 1: Write failing ownership tests**

Add a direct router test using the existing `FakeDB` pattern in `backend/tests/test_chat_agent_service_integration.py`.

```python
def test_session_history_rejects_authenticated_non_owner():
    session_id = uuid.uuid4()
    db = FakeDB(
        session=SimpleNamespace(
            id=session_id,
            user_id=7,
            title="secret",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
    )

    try:
        asyncio.run(
            chat.get_session_history(
                session_id,
                user=SimpleNamespace(id=42),
                db=db,
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "Session not found"
    else:
        raise AssertionError("foreign session history must return 404")
```

- [ ] **Step 2: Run the new failing test**

Run:

```powershell
python -m pytest backend\tests\test_chat_agent_service_integration.py::test_session_history_rejects_authenticated_non_owner -q
```

Expected: FAIL because `get_session_history` does not accept `user` yet and does not check ownership.

- [ ] **Step 3: Create the session guard helper**

Create `backend/app/services/chatbot/session_guard.py`.

```python
from fastapi import HTTPException

from app.models.chat import ChatSession
from app.models.user import User


def verify_session_ownership(session: ChatSession, user: User | None) -> None:
    """Raise 404 when an authenticated session is accessed by a non-owner."""
    if session.user_id is not None and (user is None or session.user_id != user.id):
        raise HTTPException(status_code=404, detail="Session not found")
```

- [ ] **Step 4: Use the helper in chat routes**

Modify `backend/app/routers/chat.py`:

```python
from app.services.chatbot.session_guard import verify_session_ownership
```

In `send_message`, replace the inline ownership check with:

```python
verify_session_ownership(session, user)
```

In `get_session_history`, add the dependency and helper call:

```python
async def get_session_history(
    session_id: uuid.UUID,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    verify_session_ownership(session, user)
```

- [ ] **Step 5: Verify ownership tests pass**

Run:

```powershell
python -m pytest backend\tests\test_chat_agent_service_integration.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend\app\services\chatbot\session_guard.py backend\app\routers\chat.py backend\tests\test_chat_agent_service_integration.py
git commit -m "fix: enforce chat session ownership"
```

---

### Task 2: Daily Quota and Free-Tier Abuse Guard

**Files:**
- Create: `backend/app/services/chatbot/quota.py`
- Create: `backend/app/services/chatbot/abuse_guard.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/routers/chat.py`
- Test: `backend/tests/test_chat_quota.py`
- Test: `backend/tests/test_chat_abuse_guard.py`

- [ ] **Step 1: Add config settings**

In `backend/app/config.py`, add these settings to the existing settings class:

```python
ANON_CHAT_DAILY_LIMIT: int = 20
AUTH_CHAT_DAILY_LIMIT: int = 100
CHAT_ABUSE_GUARD_ENABLED: bool = True
CHAT_ABUSE_GUARD_ANON_MAX_REQUESTS: int = 10
CHAT_ABUSE_GUARD_ANON_WINDOW_SECONDS: int = 60
CHAT_ABUSE_GUARD_AUTH_MAX_REQUESTS: int = 30
CHAT_ABUSE_GUARD_AUTH_WINDOW_SECONDS: int = 60
```

- [ ] **Step 2: Write failing quota tests**

Create `backend/tests/test_chat_quota.py` with a small fake DB result object.

```python
class CountResult:
    def __init__(self, value: int) -> None:
        self.value = value

    def scalar(self) -> int:
        return self.value


class CountDB:
    async def execute(self, query):
        return CountResult(1)


async def test_authenticated_quota_blocks_at_limit(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_CHAT_DAILY_LIMIT", "1")
    try:
        with pytest.raises(HTTPException) as exc:
            await enforce_chat_quota(
                CountDB(),
                user=SimpleNamespace(id=7),
                session_id=None,
            )
        assert exc.value.status_code == 429
    finally:
        get_settings.cache_clear()
```

- [ ] **Step 3: Write failing abuse guard tests**

Create `backend/tests/test_chat_abuse_guard.py`.

```python
def test_abuse_guard_blocks_after_threshold():
    guard = ChatAbuseGuard(max_requests=2, window_seconds=60)

    first = guard.check("anon:127.0.0.1")
    second = guard.check("anon:127.0.0.1")
    third = guard.check("anon:127.0.0.1")

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.retry_after_seconds > 0
```

- [ ] **Step 4: Run failing tests**

Run:

```powershell
python -m pytest backend\tests\test_chat_quota.py backend\tests\test_chat_abuse_guard.py -q
```

Expected: FAIL because `quota.py` and `abuse_guard.py` do not exist.

- [ ] **Step 5: Implement quota helper**

Create `backend/app/services/chatbot/quota.py`.

```python
from datetime import datetime, time, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User


def _utc_day_start() -> datetime:
    today = datetime.now(timezone.utc).date()
    return datetime.combine(today, time.min, tzinfo=timezone.utc)


async def enforce_chat_quota(
    db: AsyncSession,
    *,
    user: User | None,
    session_id: UUID | None,
) -> None:
    settings = get_settings()
    day_start = _utc_day_start()
    query = select(func.count()).select_from(ChatMessage).join(ChatSession)
    query = query.where(ChatMessage.role == "user", ChatMessage.created_at >= day_start)

    if user is not None:
        limit = settings.AUTH_CHAT_DAILY_LIMIT
        query = query.where(ChatSession.user_id == user.id)
    else:
        limit = settings.ANON_CHAT_DAILY_LIMIT
        if session_id is None:
            return
        query = query.where(ChatSession.id == session_id, ChatSession.user_id.is_(None))

    count = (await db.execute(query)).scalar() or 0
    if count >= limit:
        raise HTTPException(status_code=429, detail="Da vuot qua gioi han chat trong ngay")
```

- [ ] **Step 6: Implement abuse guard helper**

Create `backend/app/services/chatbot/abuse_guard.py`.

```python
from collections import defaultdict, deque
from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class AbuseGuardResult:
    allowed: bool
    retry_after_seconds: int


class ChatAbuseGuard:
    def __init__(self, *, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> AbuseGuardResult:
        now = monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()
        if len(hits) >= self.max_requests:
            retry_after = max(1, int(self.window_seconds - (now - hits[0])))
            return AbuseGuardResult(allowed=False, retry_after_seconds=retry_after)
        hits.append(now)
        return AbuseGuardResult(allowed=True, retry_after_seconds=0)
```

- [ ] **Step 7: Integrate guard and quota into chat flow**

In `backend/app/routers/chat.py`, create helper functions:

```python
from fastapi import Header, Request, Response
from app.services.chatbot.abuse_guard import ChatAbuseGuard
from app.services.chatbot.quota import enforce_chat_quota

_anon_guard = ChatAbuseGuard(max_requests=10, window_seconds=60)
_auth_guard = ChatAbuseGuard(max_requests=30, window_seconds=60)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce_abuse_guard(request: Request, response: Response, *, user: User | None, session_id: uuid.UUID | None) -> None:
    if user is not None:
        result = _auth_guard.check(f"user:{user.id}")
    elif session_id is not None:
        result = _anon_guard.check(f"session:{session_id}")
    else:
        result = _anon_guard.check(f"ip:{_client_ip(request)}")
    if not result.allowed:
        response.headers["Retry-After"] = str(result.retry_after_seconds)
        raise HTTPException(status_code=429, detail="Ban dang gui qua nhanh, vui long thu lai sau")
```

Update `send_message` signature:

```python
async def send_message(
    body: ChatMessageRequest,
    request: Request,
    response: Response,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
```

Call `_enforce_abuse_guard` before creating a new no-session anonymous session, and call `await enforce_chat_quota(...)` before agent execution.

- [ ] **Step 8: Verify quota and guard tests pass**

Run:

```powershell
python -m pytest backend\tests\test_chat_quota.py backend\tests\test_chat_abuse_guard.py backend\tests\test_chat_agent_service_integration.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add backend\app\config.py backend\app\routers\chat.py backend\app\services\chatbot\quota.py backend\app\services\chatbot\abuse_guard.py backend\tests\test_chat_quota.py backend\tests\test_chat_abuse_guard.py backend\tests\test_chat_agent_service_integration.py
git commit -m "feat: add chat quota and abuse guard"
```

---

### Task 3: Idempotent Observability Persistence

**Files:**
- Create: `backend/app/services/agent_service/observability.py`
- Modify: `backend/app/routers/chat.py`
- Test: `backend/tests/test_agent_observability_persistence.py`

- [ ] **Step 1: Write failing tests for trace upsert and row replacement**

Create `backend/tests/test_agent_observability_persistence.py`.

```python
async def test_observability_replay_updates_trace_and_replaces_children(db_session, chat_session):
    def make_agent_response(request_id: str, steps: list[dict]) -> AgentChatResponse:
        return AgentChatResponse(
            request_id=request_id,
            final_response="answer",
            agents_used=["property_search"],
            sources=[],
            suggested_actions=[],
            trace_summary=TraceSummary(
                intent="property_search",
                agents=["property_search"],
                source_count=0,
                latency_ms=1.0,
                warnings=[],
            ),
            full_trace={"steps": steps},
            memory_proposals=[],
            readiness={},
            evaluation_candidate={},
        )

    first = make_agent_response(request_id="req-1", steps=[{"step_name": "router", "output": {"intent": "old"}}])
    second = make_agent_response(request_id="req-1", steps=[{"step_name": "router", "output": {"intent": "new"}}])

    await persist_agent_observability(session_factory=async_session, chat_session=chat_session, user=None, response=first)
    await persist_agent_observability(session_factory=async_session, chat_session=chat_session, user=None, response=second)

    traces = (await db_session.execute(select(AgentTrace).where(AgentTrace.request_id == "req-1"))).scalars().all()
    steps = (await db_session.execute(select(AgentTraceStep).where(AgentTraceStep.request_id == "req-1"))).scalars().all()

    assert len(traces) == 1
    assert len(steps) == 1
    assert steps[0].output_json["intent"] == "new"
```

- [ ] **Step 2: Run failing observability test**

Run:

```powershell
python -m pytest backend\tests\test_agent_observability_persistence.py -q
```

Expected: FAIL because `persist_agent_observability` is still local to `chat.py` and only inserts `AgentTrace`.

- [ ] **Step 3: Implement observability helper**

Create `backend/app/services/agent_service/observability.py`.

```python
from collections.abc import Callable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_observability import AgentRetrievalEvent, AgentTrace, AgentTraceStep
from app.models.chat import ChatSession
from app.models.user import User
from app.services.agent_service.contracts import AgentChatResponse


def _truncate_json(value: Any, max_chars: int) -> Any:
    text = str(value)
    if len(text) <= max_chars:
        return value
    return {"truncated": True, "preview": text[:max_chars]}


async def persist_agent_observability(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    chat_session: ChatSession,
    user: User | None,
    response: AgentChatResponse,
) -> None:
    async with session_factory() as db:
        trace = (
            await db.execute(select(AgentTrace).where(AgentTrace.request_id == response.request_id))
        ).scalar_one_or_none()
        if trace is None:
            trace = AgentTrace(request_id=response.request_id)
            db.add(trace)
        trace.session_id = chat_session.id
        trace.user_id = user.id if user else None
        trace.intent = response.trace_summary.intent
        trace.agents_used = response.agents_used
        trace.trace_summary_json = response.trace_summary.model_dump(mode="json")
        trace.full_trace_json = response.full_trace
        trace.readiness_json = response.readiness
        trace.latency_ms = response.trace_summary.latency_ms
        trace.status = "success"

        await db.execute(delete(AgentTraceStep).where(AgentTraceStep.request_id == response.request_id))
        await db.execute(delete(AgentRetrievalEvent).where(AgentRetrievalEvent.request_id == response.request_id))

        for step in response.full_trace.get("steps", []):
            db.add(AgentTraceStep(
                request_id=response.request_id,
                step_name=str(step.get("step_name", "unknown")),
                status=str(step.get("status", "success")),
                latency_ms=float(step.get("latency_ms", 0.0) or 0.0),
                input_json=_truncate_json(step.get("input", {}), 4096),
                output_json=_truncate_json(step.get("output", {}), 16384),
                error_message=step.get("error_message"),
            ))

        await db.commit()
```

- [ ] **Step 4: Move chat route to committed chat messages then separate observability**

In `backend/app/routers/chat.py`, import `async_session` and the new helper:

```python
from app.database import async_session
from app.services.agent_service.observability import persist_agent_observability
```

After adding user and assistant messages:

```python
await db.flush()
await db.commit()
await persist_agent_observability(
    session_factory=async_session,
    chat_session=session,
    user=user,
    response=agent_response,
)
```

Remove the old local `persist_agent_observability` function from `chat.py`.

- [ ] **Step 5: Verify observability tests pass**

Run:

```powershell
python -m pytest backend\tests\test_agent_observability_persistence.py backend\tests\test_chat_agent_service_integration.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend\app\services\agent_service\observability.py backend\app\routers\chat.py backend\tests\test_agent_observability_persistence.py
git commit -m "feat: persist normalized agent observability"
```

---

### Task 4: Controlled Evaluation and Cleanup

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/routers/chat.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/agent_service/client.py`
- Test: `backend/tests/test_agent_eval_trigger.py`

- [ ] **Step 1: Add eval settings**

In `backend/app/config.py`:

```python
CHATBOT_EVAL_ENABLED: bool = False
CHATBOT_EVAL_SAMPLE_RATE: float = 0.0
CHATBOT_EVAL_SYNC_FOR_TESTS: bool = False
OBSERVABILITY_ANON_RETENTION_DAYS: int = 30
OBSERVABILITY_AUTH_RETENTION_DAYS: int = 90
OBSERVABILITY_CLEANUP_ENABLED: bool = True
```

- [ ] **Step 2: Write failing eval trigger tests**

Create `backend/tests/test_agent_eval_trigger.py`.

```python
def test_eval_disabled_does_not_schedule():
    assert should_schedule_eval(
        enabled=False,
        sample_rate=1.0,
        answer="Agent answer",
        mode="agent_graph",
    ) is False


def test_eval_skips_known_fallback_modes():
    assert should_schedule_eval(
        enabled=True,
        sample_rate=1.0,
        answer="Fallback answer",
        mode="agent_service_error",
    ) is False
```

- [ ] **Step 3: Implement eval decision helper**

Add to `backend/app/routers/chat.py` or a small helper module:

```python
import random


def should_schedule_eval(*, enabled: bool, sample_rate: float, answer: str, mode: str | None) -> bool:
    if not enabled or not answer.strip():
        return False
    if mode in {"agent_service_error", "legacy_pipeline"}:
        return False
    return random.random() < sample_rate
```

- [ ] **Step 4: Create and process EvalRun**

When scheduling eval:

```python
eval_run = EvalRun(
    request_id=agent_response.request_id,
    session_id=session.id,
    status="pending",
    evaluator="gemini",
)
db.add(eval_run)
await db.flush()
```

Use a background task that opens `async_session()` before calling the Agent Service evaluate endpoint.

- [ ] **Step 5: Add stale eval cleanup helper**

In `backend/app/services/agent_service/observability.py`:

```python
from datetime import datetime, timedelta, timezone
from sqlalchemy import update
from app.models.agent_observability import EvalRun


async def mark_stale_eval_runs_failed(db: AsyncSession) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    result = await db.execute(
        update(EvalRun)
        .where(EvalRun.status == "pending", EvalRun.created_at < cutoff)
        .values(status="failed", error_message="eval_timeout_stale")
    )
    return result.rowcount or 0
```

- [ ] **Step 6: Verify eval tests pass**

Run:

```powershell
python -m pytest backend\tests\test_agent_eval_trigger.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend\app\config.py backend\app\routers\chat.py backend\app\main.py backend\app\services\agent_service\client.py backend\app\services\agent_service\observability.py backend\tests\test_agent_eval_trigger.py
git commit -m "feat: add controlled agent evaluation"
```

---

### Task 5: Admin Observability APIs

**Files:**
- Modify: `backend/app/routers/admin.py`
- Modify: `backend/app/schemas/admin.py`
- Test: `backend/tests/test_admin_observability.py`

- [ ] **Step 1: Write failing admin route-order and detail tests**

In `backend/tests/test_admin_observability.py` add:

```python
async def test_chat_trace_search_route_is_not_captured_by_request_id(admin_client):
    response = await admin_client.get("/api/v1/admin/chat-traces/search")
    assert response.status_code != 404
```

- [ ] **Step 2: Add additive schemas**

In `backend/app/schemas/admin.py`:

```python
class AgentTraceSearchResponse(BaseModel):
    items: list[AgentTraceListItem]
    total: int


class AgentTraceDetail(AgentTraceListItem):
    full_trace_json: dict[str, Any] = Field(default_factory=dict)
    readiness_json: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_events: list[dict[str, Any]] = Field(default_factory=list)
    eval_runs: list[dict[str, Any]] = Field(default_factory=list)
```

- [ ] **Step 3: Define `/chat-traces/search` before `/{request_id}`**

In `backend/app/routers/admin.py`, place this route before `@router.get("/chat-traces/{request_id}")`:

```python
@router.get("/chat-traces/search", response_model=AgentTraceSearchResponse)
async def search_chat_traces(
    q: str | None = None,
    status: str | None = None,
    intent: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(AgentTrace)
    if status:
        query = query.where(AgentTrace.status == status)
    if intent:
        query = query.where(AgentTrace.intent == intent)
    if q:
        query = query.where(AgentTrace.request_id.ilike(f"%{q}%"))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (await db.execute(query.order_by(AgentTrace.created_at.desc()).offset(offset).limit(limit))).scalars().all()
    return {"items": rows, "total": total}
```

- [ ] **Step 4: Implement top queries and health metrics**

Use `ChatMessage` joined to `ChatSession` for recent user messages:

```python
@router.get("/top-queries")
async def top_queries(
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(ChatMessage.content, func.count(ChatMessage.id).label("count"))
        .where(ChatMessage.role == "user")
        .group_by(ChatMessage.content)
        .order_by(func.count(ChatMessage.id).desc())
        .limit(limit)
    )
    rows = (await db.execute(query)).all()
    return {"items": [{"query": content, "count": count} for content, count in rows]}
```

- [ ] **Step 5: Verify admin tests pass**

Run:

```powershell
python -m pytest backend\tests\test_admin_observability.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend\app\routers\admin.py backend\app\schemas\admin.py backend\tests\test_admin_observability.py
git commit -m "feat: expand admin agent observability"
```

---

### Task 6: Agent Service Client Resilience

**Files:**
- Modify: `backend/app/services/agent_service/client.py`
- Test: `backend/tests/test_agent_service_client.py`

- [ ] **Step 1: Write failing typed error and retry tests**

In `backend/tests/test_agent_service_client.py`:

```python
async def test_transient_network_error_retried_once_then_success():
    class FlakyTransport(httpx.AsyncBaseTransport):
        def __init__(self, outcomes):
            self.outcomes = list(outcomes)
            self.calls = 0

        async def handle_async_request(self, request):
            self.calls += 1
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    def valid_agent_response() -> dict:
        return {
            "request_id": "req-1",
            "final_response": "ok",
            "agents_used": ["property_search"],
            "sources": [],
            "suggested_actions": [],
            "trace_summary": {
                "intent": "property_search",
                "agents": ["property_search"],
                "source_count": 0,
                "latency_ms": 1,
                "warnings": [],
            },
            "full_trace": {},
            "memory_proposals": [],
            "readiness": {},
            "evaluation_candidate": {},
        }

    def valid_agent_request() -> AgentChatRequest:
        return AgentChatRequest(
            request_id="req-1",
            message="Tim nha",
            session_id="session-1",
        )

    transport = FlakyTransport([httpx.ConnectError("boom"), httpx.Response(200, json=valid_agent_response())])
    client = AgentServiceClient(base_url="http://agent", internal_key="key", timeout_seconds=1, transport=transport)

    result = await client.chat(valid_agent_request())

    assert result.request_id == "req-1"
    assert transport.calls == 2
```

- [ ] **Step 2: Add typed error**

In `backend/app/services/agent_service/client.py`:

```python
class AgentServiceError(RuntimeError):
    def __init__(self, message: str, *, error_type: str) -> None:
        super().__init__(message)
        self.error_type = error_type
```

- [ ] **Step 3: Add one retry for transient network errors**

```python
TRANSIENT_ERRORS = (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError)


async def _post_chat(self, client: httpx.AsyncClient, body: AgentChatRequest, headers: dict[str, str]) -> httpx.Response:
    return await client.post(
        f"{self.base_url}/internal/agent/chat",
        json=body.model_dump(mode="json"),
        headers=headers,
    )
```

In `chat`, retry only once for `TRANSIENT_ERRORS`; do not retry `HTTPStatusError` for 4xx.

- [ ] **Step 4: Verify client tests pass**

Run:

```powershell
python -m pytest backend\tests\test_agent_service_client.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend\app\services\agent_service\client.py backend\tests\test_agent_service_client.py
git commit -m "fix: harden agent service client errors"
```

---

### Task 7: Hardening Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run focused tests**

```powershell
python -m pytest backend\tests\test_chat_agent_service_integration.py backend\tests\test_admin_observability.py backend\tests\test_agent_service_client.py backend\tests\test_chat_quota.py backend\tests\test_chat_abuse_guard.py backend\tests\test_agent_observability_persistence.py backend\tests\test_agent_eval_trigger.py -q
```

Expected: PASS.

- [ ] **Step 2: Compile changed Python packages**

```powershell
python -m compileall backend\app agent_service
```

Expected: no syntax errors.

- [ ] **Step 3: Check Docker compose config**

```powershell
docker compose config --services
```

Expected: command exits 0 and lists services.

- [ ] **Step 4: Commit verification note if documentation changed**

If no files changed, do not create an empty commit. If implementation docs changed, commit them:

```powershell
git add docs
git commit -m "docs: record hardening verification"
```
