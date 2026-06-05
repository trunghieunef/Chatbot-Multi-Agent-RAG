# Agent Platform Chatbot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an internal Agent Service powered by LangGraph and Gemini, integrate it with the existing backend chat API, and add memory, evaluation, admin observability, UI trace improvements, and VPS deploy readiness.

**Architecture:** The existing FastAPI backend remains the public entrypoint and owner of auth, sessions, messages, preferences, quotas, and public API contracts. A new internal FastAPI Agent Service owns LangGraph orchestration, Gemini calls, RAG tool planning, trace generation, async evaluation, and memory proposals. PostgreSQL/pgvector and Redis are shared at first, with explicit table ownership and internal-service authentication.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL/pgvector, Redis, LangGraph, Google Gemini via `google-genai`, BGE-M3 retrieval, optional Cohere rerank, Next.js, TypeScript, Tailwind CSS, pytest, pytest-asyncio, Docker Compose.

---

## Scope And Plan Decomposition

The approved spec spans multiple subsystems. This master plan is split into milestone tasks that each produce testable software:

1. Agent Service foundation
2. Backend database/contracts/client integration
3. Backend chat route integration
4. LangGraph core workflow
5. Multi-source RAG tools
6. Deep specialist agents and synthesis
7. Memory system
8. Evaluation system
9. Admin observability APIs
10. ChatWidget and admin frontend
11. Deploy hardening
12. Cleanup and docs

Execute these tasks in order. Each task should end with tests and a commit.

## File Structure

### New Agent Service

- `agent_service/__init__.py`  
  Marks the internal service package.
- `agent_service/config.py`  
  Reads Agent Service settings from environment.
- `agent_service/contracts.py`  
  Defines Pydantic request/response contracts shared by graph nodes and HTTP handlers.
- `agent_service/security.py`  
  Validates `X-Internal-Agent-Key`.
- `agent_service/main.py`  
  FastAPI app exposing internal agent endpoints.
- `agent_service/graph/state.py`  
  LangGraph state schema.
- `agent_service/graph/workflow.py`  
  Builds and runs the LangGraph workflow.
- `agent_service/graph/nodes.py`  
  Graph nodes for context, readiness, routing, planning, agent execution, synthesis, memory proposal extraction, and trace building.
- `agent_service/llm/gemini.py`  
  Small Gemini client wrapper with structured output and test injection.
- `agent_service/tools/retrieval.py`  
  Traceable wrappers around existing backend RAG and analytics services.
- `agent_service/tools/readiness.py`  
  Source readiness helpers.
- `agent_service/evaluation/judge.py`  
  Async Gemini LLM-as-judge runner.
- `agent_service/Dockerfile`  
  Runtime image for the internal service.
- `agent_service/requirements.txt`  
  Runtime dependencies for the internal service.

### Backend Additions

- `backend/app/services/agent_service/contracts.py`  
  Backend-side internal Agent Service request/response schemas.
- `backend/app/services/agent_service/client.py`  
  Internal HTTP client with timeout, auth header, and fallback-safe errors.
- `backend/app/services/chatbot/context.py`  
  Selects curated conversation context instead of full history.
- `backend/app/services/chatbot/memory.py`  
  Backend-owned memory proposal apply/pending/reject rules.
- `backend/app/models/preference.py`  
  User preferences, memory proposals, and chat feedback models.
- `backend/app/models/agent_observability.py`  
  Agent traces, trace steps, LLM calls, retrieval events, eval runs, eval scores, and prompt versions.
- `backend/app/models/source_readiness.py`  
  Pipeline-owned source readiness model.
- `backend/app/schemas/preferences.py`  
  Preference and memory proposal API schemas.
- `backend/app/schemas/admin.py`  
  Admin observability API schemas.
- `backend/app/routers/preferences.py`  
  User preference and memory proposal endpoints.
- `backend/app/routers/admin.py`  
  Admin trace/eval/readiness/feedback/memory endpoints.
- `backend/alembic/versions/20260603_0010_agent_platform_tables.py`  
  Migration for backend-owned and agent-owned tables.

### Frontend Additions

- `frontend/lib/types.ts`  
  Extend chat, trace, source, feedback, preference, and admin types.
- `frontend/lib/api.ts`  
  Add feedback, preferences, memory proposals, and admin API functions.
- `frontend/components/chatbot/ChatWidget.tsx`  
  Display trace summary, richer sources, feedback, and memory hints.
- `frontend/app/admin/page.tsx`  
  Admin observability shell page.
- `frontend/components/admin/AdminDashboard.tsx`  
  Admin dashboard composed of trace, eval, readiness, health, query, feedback, and memory panels.

### Deploy Files

- `docker-compose.yml`  
  Add `agent-service` container and internal env wiring.
- `.env.example`  
  Document required deploy variables.
- `docs/deploy/google-cloud-vm.md`  
  Google Cloud VM deployment checklist and smoke tests.

---

### Task 1: Agent Service Foundation

**Files:**
- Create: `agent_service/__init__.py`
- Create: `agent_service/config.py`
- Create: `agent_service/contracts.py`
- Create: `agent_service/security.py`
- Create: `agent_service/main.py`
- Create: `agent_service/requirements.txt`
- Create: `agent_service/Dockerfile`
- Test: `backend/tests/test_agent_service_foundation.py`

- [ ] **Step 1: Write failing tests for internal auth and health/readiness endpoints**

Create `backend/tests/test_agent_service_foundation.py`:

```python
from fastapi.testclient import TestClient

from agent_service.config import get_agent_settings
from agent_service.main import app


def test_agent_settings_defaults_are_internal_safe(monkeypatch):
    get_agent_settings.cache_clear()
    monkeypatch.delenv("AGENT_INTERNAL_KEY", raising=False)
    settings = get_agent_settings()

    assert settings.AGENT_INTERNAL_KEY == "dev-agent-internal-key"
    assert settings.GEMINI_MODEL == "gemini-2.0-flash"
    assert settings.CHATBOT_TRACE_LEVEL == "full"


def test_internal_health_requires_agent_key(monkeypatch):
    get_agent_settings.cache_clear()
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret-test-key")
    client = TestClient(app)

    response = client.get("/internal/agent/health")

    assert response.status_code == 401


def test_internal_health_accepts_agent_key(monkeypatch):
    get_agent_settings.cache_clear()
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret-test-key")
    client = TestClient(app)

    response = client.get(
        "/internal/agent/health",
        headers={"X-Internal-Agent-Key": "secret-test-key"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "agent-service"


def test_internal_readiness_accepts_agent_key(monkeypatch):
    get_agent_settings.cache_clear()
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret-test-key")
    client = TestClient(app)

    response = client.get(
        "/internal/agent/readiness",
        headers={"X-Internal-Agent-Key": "secret-test-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["sources"] == {}
```

- [ ] **Step 2: Run the tests and verify they fail because `agent_service` does not exist**

Run:

```powershell
pytest backend\tests\test_agent_service_foundation.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_service'`.

- [ ] **Step 3: Create the Agent Service package and config**

Create `agent_service/__init__.py`:

```python
"""Internal Agent Service for LangGraph multi-agent RAG."""
```

Create `agent_service/config.py`:

```python
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings


class AgentSettings(BaseSettings):
    """Settings for the internal Agent Service."""

    SERVICE_NAME: str = "agent-service"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+asyncpg://admin:realestate_secret_2026@localhost:5432/realestate"
    REDIS_URL: str = "redis://localhost:6379/0"

    AGENT_INTERNAL_KEY: str = "dev-agent-internal-key"
    CHATBOT_TRACE_LEVEL: str = "full"
    AGENT_GRAPH_VERSION: str = "agent-graph-v1"
    AGENT_PROMPT_VERSION: str = "prompts-v1"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_JUDGE_MODEL: str = "gemini-2.0-flash"

    COHERE_API_KEY: str = ""
    HF_EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIM: int = 1024

    AGENT_REQUEST_TIMEOUT_SECONDS: float = 45.0
    AGENT_LLM_TIMEOUT_SECONDS: float = 30.0

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str) and value.lower() in {"release", "prod", "production"}:
            return False
        return value

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
```

- [ ] **Step 4: Create internal auth helper**

Create `agent_service/security.py`:

```python
from fastapi import Header, HTTPException, status

from agent_service.config import get_agent_settings


async def require_internal_key(
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> None:
    settings = get_agent_settings()
    if not x_internal_agent_key or x_internal_agent_key != settings.AGENT_INTERNAL_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal agent key",
        )
```

- [ ] **Step 5: Create request/response contracts**

Create `agent_service/contracts.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentSource(BaseModel):
    type: str
    id: int | None = None
    product_id: str | None = None
    title: str | None = None
    url: str | None = None
    location: str | None = None
    citation: dict[str, Any] | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationContextItem(BaseModel):
    role: str
    content: str
    created_at: str | None = None
    sources: list[AgentSource] = Field(default_factory=list)


class AgentChatRequest(BaseModel):
    request_id: str
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str
    user_id: int | None = None
    is_authenticated: bool = False
    conversation_context: list[ConversationContextItem] = Field(default_factory=list)
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    requested_trace_level: str = "full"
    locale: str = "vi-VN"


class TraceSummary(BaseModel):
    intent: str = "unknown"
    agents: list[str] = Field(default_factory=list)
    source_count: int = 0
    latency_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class MemoryProposal(BaseModel):
    action: str
    key: str
    value: Any
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: str
    requires_user_confirmation: bool = True


class AgentChatResponse(BaseModel):
    request_id: str
    final_response: str
    agents_used: list[str] = Field(default_factory=list)
    sources: list[AgentSource] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    trace_summary: TraceSummary = Field(default_factory=TraceSummary)
    full_trace: dict[str, Any] = Field(default_factory=dict)
    memory_proposals: list[MemoryProposal] = Field(default_factory=list)
    readiness: dict[str, Any] = Field(default_factory=dict)
    evaluation_candidate: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 6: Create FastAPI app**

Create `agent_service/main.py`:

```python
from fastapi import BackgroundTasks, Depends, FastAPI

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentChatRequest, AgentChatResponse, TraceSummary
from agent_service.security import require_internal_key


settings = get_agent_settings()

app = FastAPI(
    title="Real Estate Agent Service",
    version="0.1.0",
    description="Internal LangGraph multi-agent RAG service",
)


@app.get("/internal/agent/health")
async def health(_: None = Depends(require_internal_key)) -> dict:
    return {
        "status": "ok",
        "service": settings.SERVICE_NAME,
        "graph_version": settings.AGENT_GRAPH_VERSION,
    }


@app.get("/internal/agent/readiness")
async def readiness(_: None = Depends(require_internal_key)) -> dict:
    return {"status": "ok", "sources": {}}


@app.post("/internal/agent/chat", response_model=AgentChatResponse)
async def chat(
    body: AgentChatRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_internal_key),
) -> AgentChatResponse:
    del background_tasks
    return AgentChatResponse(
        request_id=body.request_id,
        final_response="Agent Service is reachable. LangGraph workflow is not wired yet.",
        agents_used=[],
        trace_summary=TraceSummary(
            intent="bootstrap",
            agents=[],
            source_count=0,
            latency_ms=0.0,
            warnings=["graph_not_wired"],
        ),
        full_trace={"request_id": body.request_id, "status": "bootstrap"},
        readiness={"status": "bootstrap"},
    )
```

- [ ] **Step 7: Create Agent Service dependencies and Dockerfile**

Create `agent_service/requirements.txt`:

```text
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
pydantic>=2.10.0
pydantic-settings>=2.7.0
python-dotenv>=1.0.0
httpx>=0.28.0
google-genai>=1.0.0
langgraph>=0.2.70
sqlalchemy[asyncio]>=2.0.36
asyncpg>=0.30.0
pgvector>=0.3.6
redis>=5.2.0
sentence-transformers>=3.0.0
prometheus-client>=0.21
```

Create `agent_service/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app:/app/backend
ENV HF_HOME=/app/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY agent_service/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY agent_service ./agent_service
COPY backend ./backend

EXPOSE 8100
CMD ["uvicorn", "agent_service.main:app", "--host", "0.0.0.0", "--port", "8100"]
```

- [ ] **Step 8: Run tests and verify foundation passes**

Run:

```powershell
pytest backend\tests\test_agent_service_foundation.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Agent Service foundation**

Run:

```powershell
git add agent_service backend\tests\test_agent_service_foundation.py
git commit -m "feat: add internal agent service foundation"
```

Expected: commit succeeds.

---

### Task 2: Backend Agent Service Contracts And Client

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/services/agent_service/__init__.py`
- Create: `backend/app/services/agent_service/contracts.py`
- Create: `backend/app/services/agent_service/client.py`
- Test: `backend/tests/test_agent_service_client.py`

- [ ] **Step 1: Write failing tests for backend settings and Agent Service client**

Create `backend/tests/test_agent_service_client.py`:

```python
import httpx
import pytest

from app.config import Settings
from app.services.agent_service.client import AgentServiceClient, AgentServiceError
from app.services.agent_service.contracts import AgentChatRequest


def test_agent_service_settings_defaults():
    settings = Settings()

    assert settings.AGENT_SERVICE_URL == "http://localhost:8100"
    assert settings.AGENT_INTERNAL_KEY == "dev-agent-internal-key"
    assert settings.CHATBOT_AGENT_SERVICE_ENABLED is False
    assert settings.CHATBOT_LLM_JUDGE_ENABLED is False
    assert settings.CHATBOT_MEMORY_ENABLED is True
    assert settings.CHATBOT_ADMIN_ENABLED is True


@pytest.mark.asyncio
async def test_agent_service_client_sends_internal_key():
    seen_headers = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["key"] = request.headers.get("X-Internal-Agent-Key")
        return httpx.Response(
            200,
            json={
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
            },
        )

    transport = httpx.MockTransport(handler)
    client = AgentServiceClient(
        base_url="http://agent-service:8100",
        internal_key="secret",
        timeout_seconds=3,
        transport=transport,
    )

    response = await client.chat(
        AgentChatRequest(
            request_id="req-1",
            message="Tim nha",
            session_id="session-1",
        )
    )

    assert seen_headers["key"] == "secret"
    assert response.final_response == "ok"
    assert response.agents_used == ["property_search"]


@pytest.mark.asyncio
async def test_agent_service_client_raises_safe_error_on_500():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = AgentServiceClient(
        base_url="http://agent-service:8100",
        internal_key="secret",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AgentServiceError) as exc:
        await client.chat(
            AgentChatRequest(
                request_id="req-1",
                message="Tim nha",
                session_id="session-1",
            )
        )

    assert "Agent Service request failed" in str(exc.value)
```

- [ ] **Step 2: Run tests and verify they fail because modules/settings do not exist**

Run:

```powershell
pytest backend\tests\test_agent_service_client.py -q
```

Expected: FAIL with missing settings or missing `app.services.agent_service`.

- [ ] **Step 3: Add backend settings**

Modify `backend/app/config.py` inside `Settings` after reranking settings:

```python
    # Internal Agent Service
    AGENT_SERVICE_URL: str = "http://localhost:8100"
    AGENT_INTERNAL_KEY: str = "dev-agent-internal-key"
    AGENT_SERVICE_TIMEOUT_SECONDS: float = 45.0
    CHATBOT_AGENT_SERVICE_ENABLED: bool = False
    CHATBOT_LLM_JUDGE_ENABLED: bool = False
    CHATBOT_MEMORY_ENABLED: bool = True
    CHATBOT_ADMIN_ENABLED: bool = True
    CHATBOT_TRACE_LEVEL: str = "full"
    GEMINI_JUDGE_MODEL: str = "gemini-2.0-flash"

    # Chat quotas
    ANON_CHAT_DAILY_LIMIT: int = 20
    AUTH_CHAT_DAILY_LIMIT: int = 200
```

- [ ] **Step 4: Create backend Agent Service contracts**

Create `backend/app/services/agent_service/__init__.py`:

```python
"""Backend client package for the internal Agent Service."""
```

Create `backend/app/services/agent_service/contracts.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentSource(BaseModel):
    type: str
    id: int | None = None
    product_id: str | None = None
    title: str | None = None
    url: str | None = None
    location: str | None = None
    citation: dict[str, Any] | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationContextItem(BaseModel):
    role: str
    content: str
    created_at: str | None = None
    sources: list[AgentSource] = Field(default_factory=list)


class AgentChatRequest(BaseModel):
    request_id: str
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str
    user_id: int | None = None
    is_authenticated: bool = False
    conversation_context: list[ConversationContextItem] = Field(default_factory=list)
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    requested_trace_level: str = "full"
    locale: str = "vi-VN"


class TraceSummary(BaseModel):
    intent: str = "unknown"
    agents: list[str] = Field(default_factory=list)
    source_count: int = 0
    latency_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class MemoryProposal(BaseModel):
    action: str
    key: str
    value: Any
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: str
    requires_user_confirmation: bool = True


class AgentChatResponse(BaseModel):
    request_id: str
    final_response: str
    agents_used: list[str] = Field(default_factory=list)
    sources: list[AgentSource] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    trace_summary: TraceSummary = Field(default_factory=TraceSummary)
    full_trace: dict[str, Any] = Field(default_factory=dict)
    memory_proposals: list[MemoryProposal] = Field(default_factory=list)
    readiness: dict[str, Any] = Field(default_factory=dict)
    evaluation_candidate: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 5: Create backend Agent Service client**

Create `backend/app/services/agent_service/client.py`:

```python
from __future__ import annotations

import httpx

from app.config import get_settings
from app.services.agent_service.contracts import AgentChatRequest, AgentChatResponse


class AgentServiceError(RuntimeError):
    """Raised when the internal Agent Service cannot return a valid response."""


class AgentServiceClient:
    def __init__(
        self,
        *,
        base_url: str,
        internal_key: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.internal_key = internal_key
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def chat(self, body: AgentChatRequest) -> AgentChatResponse:
        headers = {"X-Internal-Agent-Key": self.internal_key}
        timeout = httpx.Timeout(self.timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/internal/agent/chat",
                    json=body.model_dump(mode="json"),
                    headers=headers,
                )
                response.raise_for_status()
                return AgentChatResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise AgentServiceError(f"Agent Service request failed: {exc}") from exc


def get_agent_service_client() -> AgentServiceClient:
    settings = get_settings()
    return AgentServiceClient(
        base_url=settings.AGENT_SERVICE_URL,
        internal_key=settings.AGENT_INTERNAL_KEY,
        timeout_seconds=settings.AGENT_SERVICE_TIMEOUT_SECONDS,
    )
```

- [ ] **Step 6: Run tests and verify backend client passes**

Run:

```powershell
pytest backend\tests\test_agent_service_client.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit backend client**

Run:

```powershell
git add backend\app\config.py backend\app\services\agent_service backend\tests\test_agent_service_client.py
git commit -m "feat: add backend agent service client"
```

Expected: commit succeeds.

---

### Task 3: Database Models For Memory, Trace, Eval, Feedback, And Readiness

**Files:**
- Create: `backend/app/models/preference.py`
- Create: `backend/app/models/agent_observability.py`
- Create: `backend/app/models/source_readiness.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/20260603_0010_agent_platform_tables.py`
- Test: `backend/tests/test_agent_platform_models.py`

- [ ] **Step 1: Write failing model tests**

Create `backend/tests/test_agent_platform_models.py`:

```python
from app.database import Base
from app.models import (
    AgentTrace,
    AgentTraceStep,
    AgentLLMCall,
    AgentRetrievalEvent,
    ChatFeedback,
    EvalRun,
    EvalScore,
    MemoryProposal,
    SourceReadiness,
    UserPreference,
)


def test_agent_platform_models_are_registered():
    expected_tables = {
        "user_preferences",
        "memory_proposals",
        "chat_feedback",
        "agent_traces",
        "agent_trace_steps",
        "agent_llm_calls",
        "agent_retrieval_events",
        "eval_runs",
        "eval_scores",
        "source_readiness",
    }

    assert expected_tables.issubset(set(Base.metadata.tables))


def test_model_table_names_are_explicit():
    assert UserPreference.__tablename__ == "user_preferences"
    assert MemoryProposal.__tablename__ == "memory_proposals"
    assert ChatFeedback.__tablename__ == "chat_feedback"
    assert AgentTrace.__tablename__ == "agent_traces"
    assert AgentTraceStep.__tablename__ == "agent_trace_steps"
    assert AgentLLMCall.__tablename__ == "agent_llm_calls"
    assert AgentRetrievalEvent.__tablename__ == "agent_retrieval_events"
    assert EvalRun.__tablename__ == "eval_runs"
    assert EvalScore.__tablename__ == "eval_scores"
    assert SourceReadiness.__tablename__ == "source_readiness"
```

- [ ] **Step 2: Run model tests and verify they fail**

Run:

```powershell
pytest backend\tests\test_agent_platform_models.py -q
```

Expected: FAIL with import errors for the new model classes.

- [ ] **Step 3: Create preference models**

Create `backend/app/models/preference.py`:

```python
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    key = Column(String(100), nullable=False, index=True)
    value_json = Column(JSONB, nullable=False, default={})
    confidence = Column(Float, nullable=False, default=1.0)
    source = Column(String(50), nullable=False, default="user")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class MemoryProposal(Base):
    __tablename__ = "memory_proposals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=True, index=True)
    request_id = Column(String(80), nullable=False, index=True)
    action = Column(String(30), nullable=False)
    key = Column(String(100), nullable=False, index=True)
    value_json = Column(JSONB, nullable=False, default={})
    confidence = Column(Float, nullable=False)
    evidence = Column(Text, nullable=False)
    requires_user_confirmation = Column(Boolean, nullable=False, default=True)
    status = Column(String(30), nullable=False, default="pending")
    created_at = Column(DateTime, default=func.now())
    resolved_at = Column(DateTime, nullable=True)


class ChatFeedback(Base):
    __tablename__ = "chat_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    request_id = Column(String(80), nullable=False, index=True)
    rating = Column(String(20), nullable=False)
    issue_type = Column(String(80), nullable=True)
    comment = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime, default=func.now())
```

- [ ] **Step 4: Create agent observability models**

Create `backend/app/models/agent_observability.py`:

```python
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(80), nullable=False, unique=True, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    intent = Column(String(100), nullable=True)
    agents_used = Column(JSONB, nullable=False, default=[])
    trace_summary_json = Column(JSONB, nullable=False, default={})
    full_trace_json = Column(JSONB, nullable=False, default={})
    readiness_json = Column(JSONB, nullable=False, default={})
    latency_ms = Column(Float, nullable=False, default=0.0)
    status = Column(String(30), nullable=False, default="success")
    error_message = Column(Text, nullable=True)
    graph_version = Column(String(80), nullable=True)
    prompt_version = Column(String(80), nullable=True)
    model_name = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=func.now())


class AgentTraceStep(Base):
    __tablename__ = "agent_trace_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(80), nullable=False, index=True)
    step_name = Column(String(120), nullable=False)
    status = Column(String(30), nullable=False, default="success")
    latency_ms = Column(Float, nullable=False, default=0.0)
    input_json = Column(JSONB, nullable=False, default={})
    output_json = Column(JSONB, nullable=False, default={})
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())


class AgentLLMCall(Base):
    __tablename__ = "agent_llm_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(80), nullable=False, index=True)
    node_name = Column(String(120), nullable=False)
    model_name = Column(String(120), nullable=False)
    prompt_version = Column(String(80), nullable=True)
    latency_ms = Column(Float, nullable=False, default=0.0)
    token_input_estimate = Column(Integer, nullable=True)
    token_output_estimate = Column(Integer, nullable=True)
    status = Column(String(30), nullable=False, default="success")
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime, default=func.now())


class AgentRetrievalEvent(Base):
    __tablename__ = "agent_retrieval_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(80), nullable=False, index=True)
    tool_name = Column(String(120), nullable=False)
    parent_type = Column(String(40), nullable=True)
    filters_json = Column(JSONB, nullable=False, default={})
    result_count = Column(Integer, nullable=False, default=0)
    latency_ms = Column(Float, nullable=False, default=0.0)
    status = Column(String(30), nullable=False, default="success")
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime, default=func.now())


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(80), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=True, index=True)
    evaluator = Column(String(80), nullable=False, default="gemini")
    graph_version = Column(String(80), nullable=False)
    prompt_version = Column(String(80), nullable=False)
    model_name = Column(String(120), nullable=False)
    status = Column(String(30), nullable=False, default="pending")
    summary_json = Column(JSONB, nullable=False, default={})
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)


class EvalScore(Base):
    __tablename__ = "eval_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    eval_run_id = Column(Integer, ForeignKey("eval_runs.id"), nullable=False, index=True)
    metric = Column(String(80), nullable=False)
    score = Column(Float, nullable=False)
    rationale = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
```

- [ ] **Step 5: Create source readiness model**

Create `backend/app/models/source_readiness.py`:

```python
from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class SourceReadiness(Base):
    __tablename__ = "source_readiness"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(80), nullable=False, unique=True, index=True)
    status = Column(String(30), nullable=False, default="unknown")
    parent_count = Column(Integer, nullable=False, default=0)
    chunk_count = Column(Integer, nullable=False, default=0)
    last_indexed_at = Column(DateTime, nullable=True)
    details_json = Column(JSONB, nullable=False, default={})
    warning = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
```

- [ ] **Step 6: Register models**

Modify `backend/app/models/__init__.py`:

```python
from app.models.agent_observability import (
    AgentLLMCall,
    AgentRetrievalEvent,
    AgentTrace,
    AgentTraceStep,
    EvalRun,
    EvalScore,
)
from app.models.article import Article
from app.models.chat import ChatMessage, ChatSession
from app.models.chunk import Chunk
from app.models.listing import Listing
from app.models.pipeline_run import PipelineRun
from app.models.preference import ChatFeedback, MemoryProposal, UserPreference
from app.models.project import Project
from app.models.source_readiness import SourceReadiness
from app.models.user import User

__all__ = [
    "AgentLLMCall",
    "AgentRetrievalEvent",
    "AgentTrace",
    "AgentTraceStep",
    "Article",
    "ChatFeedback",
    "ChatMessage",
    "ChatSession",
    "Chunk",
    "EvalRun",
    "EvalScore",
    "Listing",
    "MemoryProposal",
    "PipelineRun",
    "Project",
    "SourceReadiness",
    "User",
    "UserPreference",
]
```

Modify import line in `backend/alembic/env.py`:

```python
from app.models import (
    AgentLLMCall,
    AgentRetrievalEvent,
    AgentTrace,
    AgentTraceStep,
    Article,
    ChatFeedback,
    ChatMessage,
    ChatSession,
    Chunk,
    EvalRun,
    EvalScore,
    Listing,
    MemoryProposal,
    PipelineRun,
    Project,
    SourceReadiness,
    User,
    UserPreference,
)
```

- [ ] **Step 7: Create Alembic migration**

Create `backend/alembic/versions/20260603_0010_agent_platform_tables.py`:

```python
"""agent platform tables

Revision ID: 20260603_0010
Revises: 20260801_0009
Create Date: 2026-06-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260603_0010"
down_revision = "20260801_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value_json", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"])
    op.create_index("ix_user_preferences_key", "user_preferences", ["key"])

    op.create_table(
        "memory_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id"), nullable=True),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value_json", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("requires_user_confirmation", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_memory_proposals_user_id", "memory_proposals", ["user_id"])
    op.create_index("ix_memory_proposals_session_id", "memory_proposals", ["session_id"])
    op.create_index("ix_memory_proposals_request_id", "memory_proposals", ["request_id"])
    op.create_index("ix_memory_proposals_key", "memory_proposals", ["key"])

    op.create_table(
        "chat_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id"), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("rating", sa.String(length=20), nullable=False),
        sa.Column("issue_type", sa.String(length=80), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("metadata_json", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_chat_feedback_user_id", "chat_feedback", ["user_id"])
    op.create_index("ix_chat_feedback_session_id", "chat_feedback", ["session_id"])
    op.create_index("ix_chat_feedback_request_id", "chat_feedback", ["request_id"])

    op.create_table(
        "agent_traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(length=80), nullable=False, unique=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("intent", sa.String(length=100), nullable=True),
        sa.Column("agents_used", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("trace_summary_json", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("full_trace_json", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("readiness_json", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("graph_version", sa.String(length=80), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_traces_request_id", "agent_traces", ["request_id"])
    op.create_index("ix_agent_traces_session_id", "agent_traces", ["session_id"])
    op.create_index("ix_agent_traces_user_id", "agent_traces", ["user_id"])

    op.create_table(
        "agent_trace_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("step_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="success"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("input_json", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output_json", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_trace_steps_request_id", "agent_trace_steps", ["request_id"])

    op.create_table(
        "agent_llm_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("node_name", sa.String(length=120), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("token_input_estimate", sa.Integer(), nullable=True),
        sa.Column("token_output_estimate", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_llm_calls_request_id", "agent_llm_calls", ["request_id"])

    op.create_table(
        "agent_retrieval_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("parent_type", sa.String(length=40), nullable=True),
        sa.Column("filters_json", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_retrieval_events_request_id", "agent_retrieval_events", ["request_id"])

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id"), nullable=True),
        sa.Column("evaluator", sa.String(length=80), nullable=False, server_default="gemini"),
        sa.Column("graph_version", sa.String(length=80), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("summary_json", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_eval_runs_request_id", "eval_runs", ["request_id"])
    op.create_index("ix_eval_runs_session_id", "eval_runs", ["session_id"])

    op.create_table(
        "eval_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("eval_run_id", sa.Integer(), sa.ForeignKey("eval_runs.id"), nullable=False),
        sa.Column("metric", sa.String(length=80), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_eval_scores_eval_run_id", "eval_scores", ["eval_run_id"])

    op.create_table(
        "source_readiness",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(length=80), nullable=False, unique=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="unknown"),
        sa.Column("parent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_indexed_at", sa.DateTime(), nullable=True),
        sa.Column("details_json", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("warning", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_source_readiness_source_name", "source_readiness", ["source_name"])


def downgrade() -> None:
    for table in (
        "source_readiness",
        "eval_scores",
        "eval_runs",
        "agent_retrieval_events",
        "agent_llm_calls",
        "agent_trace_steps",
        "agent_traces",
        "chat_feedback",
        "memory_proposals",
        "user_preferences",
    ):
        op.drop_table(table)
```

- [ ] **Step 8: Run model tests**

Run:

```powershell
pytest backend\tests\test_agent_platform_models.py -q
```

Expected: PASS.

- [ ] **Step 9: Compile backend models**

Run:

```powershell
python -m compileall backend\app\models backend\alembic\versions\20260603_0010_agent_platform_tables.py
```

Expected: PASS.

- [ ] **Step 10: Commit database models**

Run:

```powershell
git add backend\app\models backend\alembic\env.py backend\alembic\versions\20260603_0010_agent_platform_tables.py backend\tests\test_agent_platform_models.py
git commit -m "feat: add agent platform database models"
```

Expected: commit succeeds.

---

### Task 4: Backend Chat Integration With Feature Flag And Curated Context

**Files:**
- Modify: `backend/app/schemas/chat.py`
- Create: `backend/app/services/chatbot/context.py`
- Modify: `backend/app/routers/chat.py`
- Test: `backend/tests/test_chat_agent_service_integration.py`

- [ ] **Step 1: Write failing tests for feature-flagged Agent Service chat**

Create `backend/tests/test_chat_agent_service_integration.py`:

```python
import asyncio
import uuid
from datetime import datetime

from app.routers import chat
from app.schemas.chat import ChatMessageRequest
from app.services.agent_service.contracts import AgentChatResponse, TraceSummary


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if obj.__class__.__name__ == "ChatSession" and obj.id is None:
                obj.id = uuid.uuid4()
            if obj.__class__.__name__ == "ChatMessage" and obj.created_at is None:
                obj.created_at = datetime(2026, 1, 1)

    async def execute(self, statement):
        raise AssertionError(f"Unexpected DB execute in unit test: {statement}")


class FakeAgentClient:
    def __init__(self):
        self.request = None

    async def chat(self, body):
        self.request = body
        return AgentChatResponse(
            request_id=body.request_id,
            final_response="Agent answer",
            agents_used=["property_search", "market_analysis"],
            sources=[],
            suggested_actions=["Compare"],
            trace_summary=TraceSummary(
                intent="mixed",
                agents=["property_search", "market_analysis"],
                source_count=0,
                latency_ms=10,
                warnings=[],
            ),
            full_trace={"steps": []},
            memory_proposals=[],
            readiness={"listings": {"status": "ready"}},
            evaluation_candidate={"request_id": body.request_id},
        )


def test_send_message_uses_agent_service_when_enabled(monkeypatch):
    fake_client = FakeAgentClient()
    monkeypatch.setattr(chat, "is_agent_service_enabled", lambda: True)
    monkeypatch.setattr(chat, "get_agent_service_client", lambda: fake_client)
    monkeypatch.setattr(chat, "build_conversation_context", lambda *args, **kwargs: [])
    monkeypatch.setattr(chat, "load_user_preferences", lambda *args, **kwargs: {})
    monkeypatch.setattr(chat, "persist_agent_observability", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat, "handle_memory_proposals", lambda *args, **kwargs: [])

    response = asyncio.run(
        chat.send_message(
            ChatMessageRequest(message="Tim nha va xem thi truong"),
            user=None,
            db=FakeDB(),
        )
    )

    assert response.content == "Agent answer"
    assert response.agents_used == ["property_search", "market_analysis"]
    assert response.trace_summary["intent"] == "mixed"
    assert fake_client.request.message == "Tim nha va xem thi truong"
    assert fake_client.request.conversation_context == []


def test_send_message_falls_back_to_existing_pipeline_when_agent_service_disabled(monkeypatch):
    monkeypatch.setattr(chat, "is_agent_service_enabled", lambda: False)

    async def fake_multi_agent(message, db, session_id=None):
        return {
            "final_response": "Existing pipeline answer",
            "agent_used": "property_search",
            "sources": [],
            "suggested_actions": [],
        }

    monkeypatch.setattr(chat, "run_chat_pipeline", fake_multi_agent, raising=False)

    response = asyncio.run(
        chat.send_message(
            ChatMessageRequest(message="Tim nha"),
            user=None,
            db=FakeDB(),
        )
    )

    assert response.content == "Existing pipeline answer"
    assert response.agents_used == ["property_search"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
pytest backend\tests\test_chat_agent_service_integration.py -q
```

Expected: FAIL because `agents_used`, `trace_summary`, and helper functions do not exist.

- [ ] **Step 3: Extend chat response schema**

Modify `backend/app/schemas/chat.py` `ChatMessageResponse`:

```python
class ChatMessageResponse(BaseModel):
    """Response from the chatbot."""
    session_id: UUID
    role: str
    content: str
    agent_used: str | None = None
    agents_used: list[str] = Field(default_factory=list)
    sources: list[dict] | None = None
    suggested_actions: list[str] | None = None
    trace_summary: dict | None = None
    memory_hints: list[dict] | None = None
    feedback_id: str | None = None
    request_id: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Create curated context service**

Create `backend/app/services/chatbot/context.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage
from app.models.preference import UserPreference
from app.services.agent_service.contracts import AgentSource, ConversationContextItem


def split_agents(agent_used: str | None) -> list[str]:
    if not agent_used:
        return []
    return [agent.strip() for agent in agent_used.split(",") if agent.strip()]


async def build_conversation_context(
    db: AsyncSession,
    session_id: uuid.UUID,
    limit: int = 6,
) -> list[ConversationContextItem]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    items: list[ConversationContextItem] = []
    for message in messages:
        metadata = message.metadata_json or {}
        sources = [
            AgentSource.model_validate(source)
            for source in metadata.get("sources", [])
            if isinstance(source, dict) and source.get("type")
        ]
        items.append(
            ConversationContextItem(
                role=message.role,
                content=message.content,
                created_at=message.created_at.isoformat() if message.created_at else None,
                sources=sources,
            )
        )
    return items


async def load_user_preferences(db: AsyncSession, user_id: int | None) -> dict:
    if user_id is None:
        return {}
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
    preferences: dict[str, object] = {}
    for pref in result.scalars().all():
        preferences[pref.key] = pref.value_json
    return preferences
```

- [ ] **Step 5: Add agent-service helper functions to chat router**

Modify `backend/app/routers/chat.py` imports:

```python
import uuid

from app.config import get_settings
from app.models.agent_observability import AgentTrace
from app.models.preference import MemoryProposal
from app.services.agent_service.client import AgentServiceError, get_agent_service_client
from app.services.agent_service.contracts import AgentChatRequest, AgentChatResponse
from app.services.chatbot.context import (
    build_conversation_context,
    load_user_preferences,
    split_agents,
)
```

Add helper functions near `_run_chatbot_pipeline`:

```python
def is_agent_service_enabled() -> bool:
    return get_settings().CHATBOT_AGENT_SERVICE_ENABLED


def _legacy_response_to_agent_shape(request_id: str, result: dict) -> AgentChatResponse:
    agent_used = result.get("agent_used") or "unknown"
    return AgentChatResponse(
        request_id=request_id,
        final_response=result.get("final_response") or "Toi chua tao duoc cau tra loi phu hop.",
        agents_used=split_agents(agent_used),
        sources=result.get("sources") or [],
        suggested_actions=result.get("suggested_actions") or [],
        trace_summary={
            "intent": "legacy",
            "agents": split_agents(agent_used),
            "source_count": len(result.get("sources") or []),
            "latency_ms": 0,
            "warnings": ["legacy_pipeline"],
        },
        full_trace={"mode": "legacy"},
        memory_proposals=[],
        readiness={},
        evaluation_candidate={},
    )


async def _run_agent_service_pipeline(
    message: str,
    db: AsyncSession,
    session: ChatSession,
    user: User | None,
    request_id: str,
) -> AgentChatResponse:
    if not is_agent_service_enabled():
        legacy = await _run_chatbot_pipeline(message, db, session.id)
        return _legacy_response_to_agent_shape(request_id, legacy)

    context = await build_conversation_context(db, session.id)
    preferences = await load_user_preferences(db, user.id if user else None)
    request = AgentChatRequest(
        request_id=request_id,
        message=message,
        session_id=str(session.id),
        user_id=user.id if user else None,
        is_authenticated=user is not None,
        conversation_context=context,
        user_preferences=preferences,
        requested_trace_level=get_settings().CHATBOT_TRACE_LEVEL,
    )
    try:
        return await get_agent_service_client().chat(request)
    except AgentServiceError as exc:
        return AgentChatResponse(
            request_id=request_id,
            final_response=(
                "Chatbot dang gap loi khi goi Agent Service. "
                "Vui long thu lai sau hoac thu cau hoi don gian hon."
            ),
            agents_used=["agent_service_error"],
            sources=[],
            suggested_actions=["Thu lai sau", "Kiem tra backend logs"],
            trace_summary={
                "intent": "error",
                "agents": ["agent_service_error"],
                "source_count": 0,
                "latency_ms": 0,
                "warnings": [str(exc)],
            },
            full_trace={"error": str(exc)},
            readiness={},
        )


def persist_agent_observability(
    db: AsyncSession,
    *,
    session: ChatSession,
    user: User | None,
    response: AgentChatResponse,
) -> None:
    db.add(
        AgentTrace(
            request_id=response.request_id,
            session_id=session.id,
            user_id=user.id if user else None,
            intent=response.trace_summary.intent,
            agents_used=response.agents_used,
            trace_summary_json=response.trace_summary.model_dump(mode="json"),
            full_trace_json=response.full_trace,
            readiness_json=response.readiness,
            latency_ms=response.trace_summary.latency_ms,
            status="success",
        )
    )


def handle_memory_proposals(
    db: AsyncSession,
    *,
    session: ChatSession,
    user: User | None,
    response: AgentChatResponse,
) -> list[dict]:
    hints: list[dict] = []
    if not user:
        return hints
    for proposal in response.memory_proposals:
        status = "pending" if proposal.requires_user_confirmation else "auto_applied"
        db.add(
            MemoryProposal(
                user_id=user.id,
                session_id=session.id,
                request_id=response.request_id,
                action=proposal.action,
                key=proposal.key,
                value_json={"value": proposal.value},
                confidence=proposal.confidence,
                evidence=proposal.evidence,
                requires_user_confirmation=proposal.requires_user_confirmation,
                status=status,
            )
        )
        if proposal.requires_user_confirmation:
            hints.append(proposal.model_dump(mode="json"))
    return hints
```

- [ ] **Step 6: Update `send_message` to use Agent Service response shape**

Inside `send_message`, before running the pipeline, add:

```python
    request_id = str(uuid.uuid4())
```

Replace the pipeline call block with:

```python
    agent_response = await _run_agent_service_pipeline(
        body.message,
        db,
        session,
        user,
        request_id,
    )
    response_text = agent_response.final_response
    agents_used = agent_response.agents_used
    agent_used = ", ".join(agents_used) if agents_used else "none"
    sources = [source.model_dump(mode="json") for source in agent_response.sources]
    suggested_actions = agent_response.suggested_actions
    trace_summary = agent_response.trace_summary.model_dump(mode="json")

    persist_agent_observability(db, session=session, user=user, response=agent_response)
    memory_hints = handle_memory_proposals(
        db,
        session=session,
        user=user,
        response=agent_response,
    )
```

Update assistant metadata:

```python
        metadata_json={
            "request_id": request_id,
            "sources": sources,
            "suggested_actions": suggested_actions,
            "trace_summary": trace_summary,
            "agents_used": agents_used,
            "memory_hints": memory_hints,
        },
```

Update response:

```python
    return ChatMessageResponse(
        session_id=session.id,
        role="assistant",
        content=response_text,
        agent_used=agent_used,
        agents_used=agents_used,
        sources=sources,
        suggested_actions=suggested_actions,
        trace_summary=trace_summary,
        memory_hints=memory_hints,
        request_id=request_id,
        created_at=assistant_msg.created_at,
    )
```

- [ ] **Step 7: Run chat integration tests**

Run:

```powershell
pytest backend\tests\test_chat_agent_service_integration.py backend\tests\test_chat_router_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit chat integration**

Run:

```powershell
git add backend\app\schemas\chat.py backend\app\services\chatbot\context.py backend\app\routers\chat.py backend\tests\test_chat_agent_service_integration.py
git commit -m "feat: integrate chat route with internal agent service"
```

Expected: commit succeeds.

---

### Task 5: LangGraph Core Workflow In Agent Service

**Files:**
- Create: `agent_service/graph/__init__.py`
- Create: `agent_service/graph/state.py`
- Create: `agent_service/graph/nodes.py`
- Create: `agent_service/graph/workflow.py`
- Modify: `agent_service/main.py`
- Test: `backend/tests/test_agent_graph_core.py`

- [ ] **Step 1: Write failing tests for graph core**

Create `backend/tests/test_agent_graph_core.py`:

```python
import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph.workflow import run_agent_graph


@pytest.mark.asyncio
async def test_agent_graph_returns_trace_summary_without_llm_key(monkeypatch):
    request = AgentChatRequest(
        request_id="req-graph-1",
        message="Tim can ho Quan 7 duoi 5 ty",
        session_id="session-1",
        user_preferences={"preferred_district": {"value": "Quan 7"}},
    )

    response = await run_agent_graph(request)

    assert response.request_id == "req-graph-1"
    assert response.final_response
    assert "property_search" in response.agents_used
    assert response.trace_summary.intent == "property_search"
    assert response.full_trace["request_id"] == "req-graph-1"
    assert response.full_trace["steps"]


@pytest.mark.asyncio
async def test_agent_graph_routes_legal_question_without_llm_key():
    request = AgentChatRequest(
        request_id="req-graph-2",
        message="Tu van phap ly sang ten so do",
        session_id="session-1",
    )

    response = await run_agent_graph(request)

    assert response.agents_used == ["legal_advisor"]
    assert response.trace_summary.intent == "legal_advice"
```

- [ ] **Step 2: Run graph tests and verify they fail**

Run:

```powershell
pytest backend\tests\test_agent_graph_core.py -q
```

Expected: FAIL because graph modules do not exist.

- [ ] **Step 3: Create graph state**

Create `agent_service/graph/__init__.py`:

```python
"""LangGraph workflow package."""
```

Create `agent_service/graph/state.py`:

```python
from __future__ import annotations

from typing import Any, TypedDict

from agent_service.contracts import AgentChatRequest, AgentSource, MemoryProposal


class AgentGraphState(TypedDict, total=False):
    request: AgentChatRequest
    normalized_query: str
    intent: str
    agents_to_run: list[str]
    routing_filters: dict[str, Any]
    readiness: dict[str, Any]
    evidence: dict[str, list[dict[str, Any]]]
    agent_results: dict[str, dict[str, Any]]
    final_response: str
    sources: list[AgentSource]
    suggested_actions: list[str]
    memory_proposals: list[MemoryProposal]
    trace_steps: list[dict[str, Any]]
    warnings: list[str]
```

- [ ] **Step 4: Create deterministic graph nodes**

Create `agent_service/graph/nodes.py`:

```python
from __future__ import annotations

import time
import unicodedata
from typing import Any

from agent_service.contracts import AgentSource, MemoryProposal
from agent_service.graph.state import AgentGraphState


AGENT_ORDER = [
    "legal_advisor",
    "investment_advisor",
    "market_analysis",
    "news_agent",
    "project_agent",
    "property_search",
]


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn").lower()


def _trace_step(name: str, started: float, output: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_name": name,
        "status": "success",
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "output": output,
    }


def context_builder(state: AgentGraphState) -> AgentGraphState:
    started = time.perf_counter()
    request = state["request"]
    normalized_query = _strip_accents(request.message)
    steps = state.get("trace_steps", [])
    steps.append(_trace_step("context_builder", started, {"context_items": len(request.conversation_context)}))
    return {**state, "normalized_query": normalized_query, "trace_steps": steps}


def readiness_checker(state: AgentGraphState) -> AgentGraphState:
    started = time.perf_counter()
    readiness = {
        "listings": {"status": "unknown"},
        "projects": {"status": "unknown"},
        "news": {"status": "unknown"},
        "legal": {"status": "unknown"},
        "chunks": {"status": "unknown"},
    }
    steps = state.get("trace_steps", [])
    steps.append(_trace_step("readiness_checker", started, readiness))
    return {**state, "readiness": readiness, "trace_steps": steps}


def router_node(state: AgentGraphState) -> AgentGraphState:
    started = time.perf_counter()
    query = state["normalized_query"]
    agents: list[str] = []
    intent = "property_search"

    if any(term in query for term in ["phap ly", "luat", "thu tuc", "cong chung", "so do", "sang ten"]):
        agents.append("legal_advisor")
        intent = "legal_advice"
    if any(term in query for term in ["dau tu", "roi", "loi nhuan", "sinh loi", "rental yield"]):
        agents.append("investment_advisor")
        intent = "investment_advice"
    if any(term in query for term in ["thi truong", "xu huong", "thong ke", "gia trung binh"]):
        agents.append("market_analysis")
        intent = "market_analysis"
    if any(term in query for term in ["tin tuc", "bao chi", "cap nhat"]):
        agents.append("news_agent")
        intent = "news"
    if any(term in query for term in ["du an", "chu dau tu"]):
        agents.append("project_agent")
        intent = "project"
    if any(term in query for term in ["tim", "mua", "thue", "can ho", "nha", "dat", "quan "]):
        agents.append("property_search")

    if not agents:
        agents = ["property_search"]

    ordered = [agent for agent in AGENT_ORDER if agent in set(agents)]
    if len(ordered) > 1:
        intent = "mixed"

    steps = state.get("trace_steps", [])
    steps.append(_trace_step("router", started, {"intent": intent, "agents": ordered}))
    return {**state, "intent": intent, "agents_to_run": ordered, "routing_filters": {}, "trace_steps": steps}


def retrieval_planner_node(state: AgentGraphState) -> AgentGraphState:
    started = time.perf_counter()
    evidence = {agent: [] for agent in state["agents_to_run"]}
    steps = state.get("trace_steps", [])
    steps.append(_trace_step("retrieval_planner", started, {"planned_agents": state["agents_to_run"]}))
    return {**state, "evidence": evidence, "trace_steps": steps}


def specialist_agents_node(state: AgentGraphState) -> AgentGraphState:
    started = time.perf_counter()
    results: dict[str, dict[str, Any]] = {}
    for agent in state["agents_to_run"]:
        results[agent] = {
            "agent_name": agent,
            "content": f"{agent}: da phan tich yeu cau dua tren du lieu hien co.",
            "sources": [],
            "confidence": 0.5,
            "warnings": [],
        }
    steps = state.get("trace_steps", [])
    steps.append(_trace_step("specialist_agents", started, {"agents": list(results)}))
    return {**state, "agent_results": results, "trace_steps": steps}


def synthesizer_node(state: AgentGraphState) -> AgentGraphState:
    started = time.perf_counter()
    parts = [result["content"] for result in state.get("agent_results", {}).values()]
    answer = "\n\n".join(parts) if parts else "Toi chua co du thong tin de tra loi."
    actions = ["Lam ro ngan sach", "Bo sung khu vuc", "Xem nguon du lieu"]
    steps = state.get("trace_steps", [])
    steps.append(_trace_step("synthesizer", started, {"answer_length": len(answer)}))
    return {
        **state,
        "final_response": answer,
        "sources": [],
        "suggested_actions": actions,
        "trace_steps": steps,
    }


def memory_proposal_node(state: AgentGraphState) -> AgentGraphState:
    started = time.perf_counter()
    proposals: list[MemoryProposal] = []
    query = state["normalized_query"]
    if "quan 7" in query:
        proposals.append(
            MemoryProposal(
                action="upsert",
                key="preferred_district",
                value="Quan 7",
                confidence=0.72,
                evidence="User mentioned Quan 7 in the current request.",
                requires_user_confirmation=True,
            )
        )
    steps = state.get("trace_steps", [])
    steps.append(_trace_step("memory_proposal_extractor", started, {"proposal_count": len(proposals)}))
    return {**state, "memory_proposals": proposals, "trace_steps": steps}
```

- [ ] **Step 5: Create workflow runner**

Create `agent_service/graph/workflow.py`:

```python
from __future__ import annotations

import time

from langgraph.graph import END, StateGraph

from agent_service.contracts import AgentChatRequest, AgentChatResponse, TraceSummary
from agent_service.graph.nodes import (
    context_builder,
    memory_proposal_node,
    readiness_checker,
    retrieval_planner_node,
    router_node,
    specialist_agents_node,
    synthesizer_node,
)
from agent_service.graph.state import AgentGraphState


def build_agent_graph():
    graph = StateGraph(AgentGraphState)
    graph.add_node("context_builder", context_builder)
    graph.add_node("readiness_checker", readiness_checker)
    graph.add_node("router", router_node)
    graph.add_node("retrieval_planner", retrieval_planner_node)
    graph.add_node("specialist_agents", specialist_agents_node)
    graph.add_node("synthesizer", synthesizer_node)
    graph.add_node("memory_proposals", memory_proposal_node)

    graph.set_entry_point("context_builder")
    graph.add_edge("context_builder", "readiness_checker")
    graph.add_edge("readiness_checker", "router")
    graph.add_edge("router", "retrieval_planner")
    graph.add_edge("retrieval_planner", "specialist_agents")
    graph.add_edge("specialist_agents", "synthesizer")
    graph.add_edge("synthesizer", "memory_proposals")
    graph.add_edge("memory_proposals", END)
    return graph.compile()


chat_graph = build_agent_graph()


async def run_agent_graph(request: AgentChatRequest) -> AgentChatResponse:
    started = time.perf_counter()
    result = await chat_graph.ainvoke({"request": request, "trace_steps": [], "warnings": []})
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    agents = result.get("agents_to_run", [])
    sources = result.get("sources", [])
    trace_summary = TraceSummary(
        intent=result.get("intent", "unknown"),
        agents=agents,
        source_count=len(sources),
        latency_ms=latency_ms,
        warnings=result.get("warnings", []),
    )
    return AgentChatResponse(
        request_id=request.request_id,
        final_response=result.get("final_response", ""),
        agents_used=agents,
        sources=sources,
        suggested_actions=result.get("suggested_actions", []),
        trace_summary=trace_summary,
        full_trace={
            "request_id": request.request_id,
            "steps": result.get("trace_steps", []),
            "agent_results": result.get("agent_results", {}),
        },
        memory_proposals=result.get("memory_proposals", []),
        readiness=result.get("readiness", {}),
        evaluation_candidate={
            "request_id": request.request_id,
            "answer": result.get("final_response", ""),
            "agents_used": agents,
            "source_count": len(sources),
        },
    )
```

- [ ] **Step 6: Wire Agent Service `/chat` endpoint to graph**

Modify `agent_service/main.py` imports:

```python
from agent_service.graph.workflow import run_agent_graph
```

Replace the body of `chat()`:

```python
    response = await run_agent_graph(body)
    return response
```

- [ ] **Step 7: Run graph tests**

Run:

```powershell
pytest backend\tests\test_agent_graph_core.py backend\tests\test_agent_service_foundation.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit graph core**

Run:

```powershell
git add agent_service\graph agent_service\main.py backend\tests\test_agent_graph_core.py
git commit -m "feat: add langgraph agent workflow core"
```

Expected: commit succeeds.

---

### Task 6: Multi-Source RAG Tools

**Files:**
- Create: `agent_service/tools/__init__.py`
- Create: `agent_service/tools/retrieval.py`
- Create: `agent_service/tools/readiness.py`
- Modify: `agent_service/graph/nodes.py`
- Test: `backend/tests/test_agent_rag_tools.py`

- [ ] **Step 1: Write failing tests for traceable retrieval wrappers**

Create `backend/tests/test_agent_rag_tools.py`:

```python
import pytest

from agent_service.tools.retrieval import RetrievalTrace, search_articles, search_listings
from agent_service.tools.readiness import build_readiness_snapshot


@pytest.mark.asyncio
async def test_search_listings_records_trace(monkeypatch):
    async def fake_hybrid_search(query, filters=None, parent_type="listing", top_k=20, rerank_to=5):
        assert parent_type == "listing"
        return [{"id": 1, "title": "Can ho Quan 7", "matched_chunk": {"distance": 0.2}}]

    monkeypatch.setattr("agent_service.tools.retrieval.hybrid_search", fake_hybrid_search)
    trace = RetrievalTrace(request_id="req-1")

    results = await search_listings("Tim nha", {"district": "Quan 7"}, trace)

    assert results[0]["title"] == "Can ho Quan 7"
    assert trace.events[0]["tool_name"] == "search_listings"
    assert trace.events[0]["result_count"] == 1


@pytest.mark.asyncio
async def test_search_articles_uses_parent_type_article(monkeypatch):
    called = {}

    async def fake_hybrid_search(query, filters=None, parent_type="listing", top_k=20, rerank_to=5):
        called["parent_type"] = parent_type
        called["filters"] = filters
        return [{"id": 7, "title": "Tin thi truong"}]

    monkeypatch.setattr("agent_service.tools.retrieval.hybrid_search", fake_hybrid_search)
    trace = RetrievalTrace(request_id="req-1")

    await search_articles("tin thi truong", {"category": "news"}, trace)

    assert called == {"parent_type": "article", "filters": {"category": "news"}}


@pytest.mark.asyncio
async def test_build_readiness_snapshot_returns_default_when_db_unavailable(monkeypatch):
    async def exploding_count_source(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr("agent_service.tools.readiness.count_source", exploding_count_source)

    snapshot = await build_readiness_snapshot()

    assert snapshot["listings"]["status"] == "unknown"
    assert snapshot["legal"]["status"] == "unknown"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
pytest backend\tests\test_agent_rag_tools.py -q
```

Expected: FAIL because tool modules do not exist.

- [ ] **Step 3: Create retrieval tools**

Create `agent_service/tools/__init__.py`:

```python
"""Traceable tools for Agent Service graph nodes."""
```

Create `agent_service/tools/retrieval.py`:

```python
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.services.rag.hybrid_search import hybrid_search


@dataclass
class RetrievalTrace:
    request_id: str
    events: list[dict[str, Any]] = field(default_factory=list)

    def add_event(
        self,
        *,
        tool_name: str,
        parent_type: str | None,
        filters: dict[str, Any],
        result_count: int,
        latency_ms: float,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        self.events.append(
            {
                "request_id": self.request_id,
                "tool_name": tool_name,
                "parent_type": parent_type,
                "filters": filters,
                "result_count": result_count,
                "latency_ms": latency_ms,
                "status": status,
                "error_message": error_message,
            }
        )


async def _run_hybrid_tool(
    *,
    tool_name: str,
    query: str,
    filters: dict[str, Any],
    parent_type: str,
    trace: RetrievalTrace,
    top_k: int = 20,
    rerank_to: int = 5,
) -> list[dict[str, Any]]:
    started = time.perf_counter()
    try:
        results = await hybrid_search(
            query=query,
            filters=filters,
            parent_type=parent_type,
            top_k=top_k,
            rerank_to=rerank_to,
        )
        trace.add_event(
            tool_name=tool_name,
            parent_type=parent_type,
            filters=filters,
            result_count=len(results),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return results
    except Exception as exc:
        trace.add_event(
            tool_name=tool_name,
            parent_type=parent_type,
            filters=filters,
            result_count=0,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            status="error",
            error_message=str(exc),
        )
        return []


async def search_listings(query: str, filters: dict[str, Any], trace: RetrievalTrace) -> list[dict[str, Any]]:
    return await _run_hybrid_tool(
        tool_name="search_listings",
        query=query,
        filters=filters,
        parent_type="listing",
        trace=trace,
    )


async def search_projects(query: str, filters: dict[str, Any], trace: RetrievalTrace) -> list[dict[str, Any]]:
    return await _run_hybrid_tool(
        tool_name="search_projects",
        query=query,
        filters=filters,
        parent_type="project",
        trace=trace,
    )


async def search_articles(query: str, filters: dict[str, Any], trace: RetrievalTrace) -> list[dict[str, Any]]:
    return await _run_hybrid_tool(
        tool_name="search_articles",
        query=query,
        filters=filters,
        parent_type="article",
        trace=trace,
    )
```

- [ ] **Step 4: Create readiness tools**

Create `agent_service/tools/readiness.py`:

```python
from __future__ import annotations

from sqlalchemy import func, select

from app.database import async_session
from app.models import Article, Chunk, Listing, Project


async def count_source(source_name: str) -> dict:
    async with async_session() as session:
        if source_name == "listings":
            parent_count = (await session.execute(select(func.count(Listing.id)))).scalar() or 0
            chunk_count = (
                await session.execute(select(func.count(Chunk.id)).where(Chunk.parent_type == "listing"))
            ).scalar() or 0
        elif source_name == "projects":
            parent_count = (await session.execute(select(func.count(Project.id)))).scalar() or 0
            chunk_count = (
                await session.execute(select(func.count(Chunk.id)).where(Chunk.parent_type == "project"))
            ).scalar() or 0
        elif source_name == "news":
            parent_count = (
                await session.execute(select(func.count(Article.id)).where(Article.category != "legal"))
            ).scalar() or 0
            chunk_count = (
                await session.execute(select(func.count(Chunk.id)).where(Chunk.parent_type == "article"))
            ).scalar() or 0
        elif source_name == "legal":
            parent_count = (
                await session.execute(select(func.count(Article.id)).where(Article.category == "legal"))
            ).scalar() or 0
            chunk_count = (
                await session.execute(select(func.count(Chunk.id)).where(Chunk.parent_type == "article"))
            ).scalar() or 0
        else:
            parent_count = 0
            chunk_count = 0
    status = "ready" if parent_count > 0 and chunk_count > 0 else "not_ready"
    return {"status": status, "parent_count": parent_count, "chunk_count": chunk_count}


async def build_readiness_snapshot() -> dict[str, dict]:
    snapshot: dict[str, dict] = {}
    for source_name in ("listings", "projects", "news", "legal"):
        try:
            snapshot[source_name] = await count_source(source_name)
        except Exception as exc:
            snapshot[source_name] = {
                "status": "unknown",
                "parent_count": 0,
                "chunk_count": 0,
                "warning": str(exc),
            }
    return snapshot
```

- [ ] **Step 5: Update graph readiness checker to use readiness tool**

Modify `agent_service/graph/nodes.py`:

```python
from agent_service.tools.readiness import build_readiness_snapshot
```

Replace `readiness_checker` with an async version:

```python
async def readiness_checker(state: AgentGraphState) -> AgentGraphState:
    started = time.perf_counter()
    readiness = await build_readiness_snapshot()
    steps = state.get("trace_steps", [])
    steps.append(_trace_step("readiness_checker", started, readiness))
    return {**state, "readiness": readiness, "trace_steps": steps}
```

- [ ] **Step 6: Run RAG tool and graph tests**

Run:

```powershell
pytest backend\tests\test_agent_rag_tools.py backend\tests\test_agent_graph_core.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit RAG tools**

Run:

```powershell
git add agent_service\tools agent_service\graph\nodes.py backend\tests\test_agent_rag_tools.py
git commit -m "feat: add traceable multi-source rag tools"
```

Expected: commit succeeds.

---

### Task 7: Gemini Client, Specialist Agents, Evidence Merge, And Safety Validation

**Files:**
- Create: `agent_service/llm/__init__.py`
- Create: `agent_service/llm/gemini.py`
- Create: `agent_service/agents/__init__.py`
- Create: `agent_service/agents/specialists.py`
- Modify: `agent_service/graph/nodes.py`
- Test: `backend/tests/test_agent_specialists.py`

- [ ] **Step 1: Write failing tests for specialist agent behavior**

Create `backend/tests/test_agent_specialists.py`:

```python
import pytest

from agent_service.agents.specialists import (
    run_investment_agent,
    run_legal_agent,
    run_property_agent,
)


@pytest.mark.asyncio
async def test_property_agent_requires_evidence_for_listing_claims():
    result = await run_property_agent(
        query="Tim can ho Quan 7",
        evidence=[
            {
                "id": 1,
                "title": "Can ho Quan 7",
                "district": "Quan 7",
                "city": "Ho Chi Minh",
                "price_text": "4.8 ty",
                "area_text": "70 m2",
                "url": "https://example.test/1",
            }
        ],
        preferences={},
        readiness={"listings": {"status": "ready"}},
    )

    assert result["agent_name"] == "property_search"
    assert "Can ho Quan 7" in result["content"]
    assert result["sources"][0]["type"] == "listing"
    assert result["confidence"] >= 0.7


@pytest.mark.asyncio
async def test_legal_agent_warns_when_legal_kb_not_ready():
    result = await run_legal_agent(
        query="Sang ten so do can gi",
        evidence=[],
        preferences={},
        readiness={"legal": {"status": "not_ready"}},
    )

    assert result["agent_name"] == "legal_advisor"
    assert "chua san sang" in result["content"].lower()
    assert result["warnings"]


@pytest.mark.asyncio
async def test_investment_agent_includes_financial_disclaimer():
    result = await run_investment_agent(
        query="Dau tu can ho Quan 7",
        evidence=[],
        preferences={"risk_preferences": {"value": "conservative"}},
        readiness={"listings": {"status": "ready"}},
    )

    assert result["agent_name"] == "investment_advisor"
    assert "khong phai loi khuyen tai chinh" in result["content"].lower()
```

- [ ] **Step 2: Run specialist tests and verify they fail**

Run:

```powershell
pytest backend\tests\test_agent_specialists.py -q
```

Expected: FAIL because specialist modules do not exist.

- [ ] **Step 3: Create Gemini wrapper**

Create `agent_service/llm/__init__.py`:

```python
"""LLM clients for Agent Service."""
```

Create `agent_service/llm/gemini.py`:

```python
from __future__ import annotations

import json
from typing import Any

from agent_service.config import get_agent_settings


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        settings = get_agent_settings()
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL

    async def generate_text(self, prompt: str) -> str:
        if not self.api_key:
            return ""
        from google import genai

        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(model=self.model, contents=prompt)
        return response.text or ""

    async def generate_json(self, prompt: str) -> dict[str, Any]:
        text = await self.generate_text(prompt)
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}
```

- [ ] **Step 4: Create specialist agents**

Create `agent_service/agents/__init__.py`:

```python
"""Specialist agent implementations."""
```

Create `agent_service/agents/specialists.py`:

```python
from __future__ import annotations

from typing import Any


def _source_from_record(record: dict[str, Any], source_type: str) -> dict[str, Any]:
    location = ", ".join(part for part in [record.get("district"), record.get("city")] if part)
    return {
        "type": source_type,
        "id": record.get("id"),
        "product_id": record.get("product_id"),
        "title": record.get("title") or record.get("name"),
        "url": record.get("url"),
        "location": location or None,
        "citation": record.get("citation"),
        "score": ((record.get("matched_chunk") or {}).get("rerank_score")),
        "metadata": {
            "price_text": record.get("price_text") or record.get("price_range"),
            "area_text": record.get("area_text") or record.get("area_range"),
            "category": record.get("category"),
        },
    }


async def run_property_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    if not evidence:
        return {
            "agent_name": "property_search",
            "content": "Toi chua tim thay tin dang phu hop. Hay thu noi rong khu vuc, ngan sach hoac dien tich.",
            "sources": [],
            "confidence": 0.35,
            "warnings": ["no_listing_evidence"],
        }
    lines = [f'Tim thay {len(evidence)} tin dang phu hop voi yeu cau "{query}":']
    for index, item in enumerate(evidence[:5], start=1):
        details = " - ".join(part for part in [item.get("price_text"), item.get("area_text")] if part)
        location = ", ".join(part for part in [item.get("district"), item.get("city")] if part)
        lines.append(f"{index}. {item.get('title') or 'Tin bat dong san'} - {location or 'Chua ro vi tri'} ({details or 'chua ro gia/dien tich'})")
    lines.append("Nen kiem tra lai phap ly, tinh trang tin dang va thong tin lien he truoc khi giao dich.")
    return {
        "agent_name": "property_search",
        "content": "\n".join(lines),
        "sources": [_source_from_record(record, "listing") for record in evidence],
        "confidence": 0.8,
        "warnings": [],
    }


async def run_project_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    if readiness.get("projects", {}).get("status") != "ready" and not evidence:
        return {
            "agent_name": "project_agent",
            "content": "Du lieu du an chua san sang de tra cuu chi tiet. Toi co the tra loi bang nguon listing/news neu ban muon.",
            "sources": [],
            "confidence": 0.3,
            "warnings": ["project_source_not_ready"],
        }
    lines = [f'Phan tich du an lien quan den "{query}":']
    for index, item in enumerate(evidence[:5], start=1):
        lines.append(f"{index}. {item.get('name') or item.get('title') or 'Du an'} - {item.get('district') or ''}, {item.get('city') or ''}")
    return {
        "agent_name": "project_agent",
        "content": "\n".join(lines),
        "sources": [_source_from_record(record, "project") for record in evidence],
        "confidence": 0.75 if evidence else 0.4,
        "warnings": [],
    }


async def run_market_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    return {
        "agent_name": "market_analysis",
        "content": "Phan tich thi truong dua tren snapshot du lieu hien co. Neu chua co time-series, day khong phai xu huong lich su.",
        "sources": evidence,
        "confidence": 0.65,
        "warnings": ["snapshot_not_time_series"],
    }


async def run_news_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    if not evidence:
        return {
            "agent_name": "news_agent",
            "content": "Toi chua tim thay tin tuc phu hop trong kho bai viet da index.",
            "sources": [],
            "confidence": 0.35,
            "warnings": ["no_news_evidence"],
        }
    return {
        "agent_name": "news_agent",
        "content": "Cac tin tuc lien quan: " + "; ".join((item.get("title") or "Bai viet") for item in evidence[:3]),
        "sources": [_source_from_record(record, "news_article") for record in evidence],
        "confidence": 0.7,
        "warnings": [],
    }


async def run_legal_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    if readiness.get("legal", {}).get("status") != "ready" and not evidence:
        return {
            "agent_name": "legal_advisor",
            "content": (
                "Kho tri thuc phap ly chua san sang, nen toi khong the trich dan dieu luat cu the. "
                "Ban nen kiem tra so do, quy hoach/tranh chap, hop dong dat coc, thue phi va lich cong chung/sang ten. "
                "Noi dung nay chi mang tinh tham khao."
            ),
            "sources": [],
            "confidence": 0.4,
            "warnings": ["legal_kb_not_ready"],
        }
    return {
        "agent_name": "legal_advisor",
        "content": "Ket qua phap ly tham khao: " + "; ".join((item.get("title") or "Nguon phap ly") for item in evidence[:3]),
        "sources": [_source_from_record(record, "legal_article") for record in evidence],
        "confidence": 0.8,
        "warnings": [],
    }


async def run_investment_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    risk = preferences.get("risk_preferences", {}).get("value", "balanced")
    return {
        "agent_name": "investment_advisor",
        "content": (
            f"Voi khau vi rui ro {risk}, nen so sanh gia mua, kha nang cho thue, thanh khoan, "
            "phap ly va bien an toan dong tien. Day khong phai loi khuyen tai chinh chinh thuc."
        ),
        "sources": evidence,
        "confidence": 0.65,
        "warnings": ["not_financial_advice"],
    }
```

- [ ] **Step 5: Update graph specialist node to call specialist agents**

Modify `agent_service/graph/nodes.py` imports:

```python
from agent_service.agents.specialists import (
    run_investment_agent,
    run_legal_agent,
    run_market_agent,
    run_news_agent,
    run_project_agent,
    run_property_agent,
)
```

Replace `specialist_agents_node` with:

```python
async def specialist_agents_node(state: AgentGraphState) -> AgentGraphState:
    started = time.perf_counter()
    runners = {
        "property_search": run_property_agent,
        "project_agent": run_project_agent,
        "market_analysis": run_market_agent,
        "news_agent": run_news_agent,
        "legal_advisor": run_legal_agent,
        "investment_advisor": run_investment_agent,
    }
    results: dict[str, dict[str, Any]] = {}
    request = state["request"]
    for agent in state["agents_to_run"]:
        runner = runners[agent]
        results[agent] = await runner(
            query=request.message,
            evidence=state.get("evidence", {}).get(agent, []),
            preferences=request.user_preferences,
            readiness=state.get("readiness", {}),
        )
    steps = state.get("trace_steps", [])
    steps.append(_trace_step("specialist_agents", started, {"agents": list(results)}))
    return {**state, "agent_results": results, "trace_steps": steps}
```

Replace `synthesizer_node` with:

```python
def synthesizer_node(state: AgentGraphState) -> AgentGraphState:
    started = time.perf_counter()
    results = state.get("agent_results", {})
    parts = []
    sources: list[AgentSource] = []
    warnings: list[str] = list(state.get("warnings", []))
    for result in results.values():
        if result.get("content"):
            parts.append(result["content"])
        warnings.extend(result.get("warnings") or [])
        for source in result.get("sources") or []:
            if isinstance(source, AgentSource):
                sources.append(source)
            else:
                sources.append(AgentSource.model_validate(source))
    answer = "\n\n".join(parts) if parts else "Toi chua co du thong tin de tra loi."
    actions = ["So sanh lua chon", "Hoi them ve phap ly", "Xem xu huong khu vuc"]
    steps = state.get("trace_steps", [])
    steps.append(_trace_step("synthesizer", started, {"answer_length": len(answer), "source_count": len(sources)}))
    return {
        **state,
        "final_response": answer,
        "sources": sources,
        "suggested_actions": actions,
        "warnings": warnings,
        "trace_steps": steps,
    }
```

- [ ] **Step 6: Run specialist and graph tests**

Run:

```powershell
pytest backend\tests\test_agent_specialists.py backend\tests\test_agent_graph_core.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit specialist agents**

Run:

```powershell
git add agent_service\llm agent_service\agents agent_service\graph\nodes.py backend\tests\test_agent_specialists.py
git commit -m "feat: add grounded specialist agents"
```

Expected: commit succeeds.

---

### Task 8: Memory System APIs And Backend Rules

**Files:**
- Create: `backend/app/schemas/preferences.py`
- Create: `backend/app/services/chatbot/memory.py`
- Create: `backend/app/routers/preferences.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_memory_preferences.py`

- [ ] **Step 1: Write failing tests for memory proposal rules**

Create `backend/tests/test_memory_preferences.py`:

```python
from types import SimpleNamespace

from app.services.agent_service.contracts import MemoryProposal
from app.services.chatbot.memory import decide_memory_status


def test_high_confidence_non_confirmation_memory_auto_applies():
    proposal = MemoryProposal(
        action="upsert",
        key="preferred_district",
        value="Quan 7",
        confidence=0.9,
        evidence="Repeated user preference",
        requires_user_confirmation=False,
    )

    assert decide_memory_status(proposal) == "auto_applied"


def test_low_confidence_memory_stays_pending():
    proposal = MemoryProposal(
        action="upsert",
        key="preferred_district",
        value="Quan 7",
        confidence=0.5,
        evidence="Single mention",
        requires_user_confirmation=False,
    )

    assert decide_memory_status(proposal) == "pending"


def test_sensitive_memory_requires_pending_confirmation():
    proposal = MemoryProposal(
        action="upsert",
        key="risk_preferences",
        value="growth",
        confidence=0.95,
        evidence="User said they like risk",
        requires_user_confirmation=True,
    )

    assert decide_memory_status(proposal) == "pending"
```

- [ ] **Step 2: Run memory tests and verify they fail**

Run:

```powershell
pytest backend\tests\test_memory_preferences.py -q
```

Expected: FAIL because `app.services.chatbot.memory` does not exist.

- [ ] **Step 3: Create preference schemas**

Create `backend/app/schemas/preferences.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UserPreferenceResponse(BaseModel):
    id: int
    key: str
    value_json: dict[str, Any]
    confidence: float
    source: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class UserPreferenceUpdate(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    value_json: dict[str, Any]


class MemoryProposalResponse(BaseModel):
    id: int
    request_id: str
    action: str
    key: str
    value_json: dict[str, Any]
    confidence: float
    evidence: str
    requires_user_confirmation: bool
    status: str
    created_at: datetime | None = None
    resolved_at: datetime | None = None

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Create memory rule service**

Create `backend/app/services/chatbot/memory.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preference import MemoryProposal as MemoryProposalModel
from app.models.preference import UserPreference
from app.services.agent_service.contracts import MemoryProposal


AUTO_APPLY_KEYS = {
    "preferred_city",
    "preferred_district",
    "preferred_property_type",
    "budget_max",
    "budget_min",
}


def decide_memory_status(proposal: MemoryProposal) -> str:
    if proposal.requires_user_confirmation:
        return "pending"
    if proposal.key in AUTO_APPLY_KEYS and proposal.confidence >= 0.8:
        return "auto_applied"
    return "pending"


async def apply_memory_proposal(
    db: AsyncSession,
    *,
    proposal: MemoryProposalModel,
) -> None:
    proposal.status = "accepted"
    proposal.resolved_at = datetime.now(timezone.utc)
    existing = None
    # Keep this as a deterministic upsert-like flow for async SQLAlchemy tests.
    from sqlalchemy import select

    result = await db.execute(
        select(UserPreference).where(
            UserPreference.user_id == proposal.user_id,
            UserPreference.key == proposal.key,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value_json = proposal.value_json
        existing.confidence = proposal.confidence
        existing.source = "agent_proposal"
    else:
        db.add(
            UserPreference(
                user_id=proposal.user_id,
                key=proposal.key,
                value_json=proposal.value_json,
                confidence=proposal.confidence,
                source="agent_proposal",
            )
        )
```

- [ ] **Step 5: Create preferences router**

Create `backend/app/routers/preferences.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.preference import MemoryProposal, UserPreference
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.preferences import (
    MemoryProposalResponse,
    UserPreferenceResponse,
    UserPreferenceUpdate,
)
from app.services.chatbot.memory import apply_memory_proposal


router = APIRouter(prefix="/preferences", tags=["Preferences"])
memory_router = APIRouter(prefix="/memory-proposals", tags=["Memory Proposals"])


@router.get("", response_model=list[UserPreferenceResponse])
async def list_preferences(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == user.id))
    return list(result.scalars().all())


@router.patch("", response_model=UserPreferenceResponse)
async def upsert_preference(
    body: UserPreferenceUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserPreference).where(
            UserPreference.user_id == user.id,
            UserPreference.key == body.key,
        )
    )
    preference = result.scalar_one_or_none()
    if preference:
        preference.value_json = body.value_json
        preference.confidence = 1.0
        preference.source = "user"
    else:
        preference = UserPreference(
            user_id=user.id,
            key=body.key,
            value_json=body.value_json,
            confidence=1.0,
            source="user",
        )
        db.add(preference)
    await db.flush()
    return preference


@memory_router.post("/{proposal_id}/accept", response_model=MemoryProposalResponse)
async def accept_memory_proposal(
    proposal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MemoryProposal).where(
            MemoryProposal.id == proposal_id,
            MemoryProposal.user_id == user.id,
        )
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Memory proposal not found")
    await apply_memory_proposal(db, proposal=proposal)
    await db.flush()
    return proposal


@memory_router.post("/{proposal_id}/reject", response_model=MemoryProposalResponse)
async def reject_memory_proposal(
    proposal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MemoryProposal).where(
            MemoryProposal.id == proposal_id,
            MemoryProposal.user_id == user.id,
        )
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Memory proposal not found")
    proposal.status = "rejected"
    proposal.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return proposal
```

- [ ] **Step 6: Include routers in backend app**

Modify `backend/app/main.py` imports:

```python
from app.routers import auth, chat, listings, market, metrics, preferences
```

Add after chat router:

```python
app.include_router(preferences.router, prefix="/api/v1")
app.include_router(preferences.memory_router, prefix="/api/v1")
```

- [ ] **Step 7: Use memory rule in chat router**

Modify `handle_memory_proposals` in `backend/app/routers/chat.py` to import and use:

```python
from app.services.chatbot.memory import decide_memory_status
```

Replace status assignment:

```python
        status = decide_memory_status(proposal)
```

- [ ] **Step 8: Run memory tests**

Run:

```powershell
pytest backend\tests\test_memory_preferences.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit memory system**

Run:

```powershell
git add backend\app\schemas\preferences.py backend\app\services\chatbot\memory.py backend\app\routers\preferences.py backend\app\main.py backend\app\routers\chat.py backend\tests\test_memory_preferences.py
git commit -m "feat: add user preference memory APIs"
```

Expected: commit succeeds.

---

### Task 9: Async Evaluation System

**Files:**
- Create: `agent_service/evaluation/__init__.py`
- Create: `agent_service/evaluation/judge.py`
- Modify: `agent_service/main.py`
- Test: `backend/tests/test_agent_evaluation.py`

- [ ] **Step 1: Write failing tests for judge payload and fallback scoring**

Create `backend/tests/test_agent_evaluation.py`:

```python
import pytest

from agent_service.evaluation.judge import build_judge_prompt, fallback_scores


def test_build_judge_prompt_includes_versions_and_metrics():
    prompt = build_judge_prompt(
        question="Tim can ho Quan 7",
        answer="Co 1 can ho phu hop.",
        sources=[{"type": "listing", "title": "Can ho"}],
        trace={"steps": []},
        graph_version="graph-v1",
        prompt_version="prompts-v1",
        model_name="gemini-2.0-flash",
    )

    assert "groundedness" in prompt
    assert "citation_quality" in prompt
    assert "graph-v1" in prompt
    assert "prompts-v1" in prompt


def test_fallback_scores_are_safe_when_judge_unavailable():
    scores = fallback_scores("judge disabled")

    assert scores["status"] == "skipped"
    assert scores["scores"]["groundedness"]["score"] == 0.0
    assert "judge disabled" in scores["scores"]["groundedness"]["rationale"]
```

- [ ] **Step 2: Run eval tests and verify they fail**

Run:

```powershell
pytest backend\tests\test_agent_evaluation.py -q
```

Expected: FAIL because `agent_service.evaluation` does not exist.

- [ ] **Step 3: Create evaluation module**

Create `agent_service/evaluation/__init__.py`:

```python
"""Evaluation helpers for Agent Service."""
```

Create `agent_service/evaluation/judge.py`:

```python
from __future__ import annotations

import json
from typing import Any

from agent_service.llm.gemini import GeminiClient


METRICS = ("groundedness", "helpfulness", "citation_quality", "safety", "trace_completeness")


def build_judge_prompt(
    *,
    question: str,
    answer: str,
    sources: list[dict[str, Any]],
    trace: dict[str, Any],
    graph_version: str,
    prompt_version: str,
    model_name: str,
) -> str:
    return (
        "You are judging a Vietnamese real-estate RAG chatbot answer. "
        "Return JSON only with scores from 0 to 1 and rationales for: "
        "groundedness, helpfulness, citation_quality, safety, trace_completeness.\n"
        f"graph_version: {graph_version}\n"
        f"prompt_version: {prompt_version}\n"
        f"model_name: {model_name}\n"
        f"question: {question}\n"
        f"answer: {answer}\n"
        f"sources: {json.dumps(sources, ensure_ascii=False)}\n"
        f"trace: {json.dumps(trace, ensure_ascii=False)}\n"
    )


def fallback_scores(reason: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "scores": {
            metric: {"score": 0.0, "rationale": reason}
            for metric in METRICS
        },
    }


async def judge_answer(
    *,
    question: str,
    answer: str,
    sources: list[dict[str, Any]],
    trace: dict[str, Any],
    graph_version: str,
    prompt_version: str,
    model_name: str,
    client: GeminiClient | None = None,
) -> dict[str, Any]:
    llm = client or GeminiClient(model=model_name)
    prompt = build_judge_prompt(
        question=question,
        answer=answer,
        sources=sources,
        trace=trace,
        graph_version=graph_version,
        prompt_version=prompt_version,
        model_name=model_name,
    )
    data = await llm.generate_json(prompt)
    if not data:
        return fallback_scores("judge unavailable")
    return {"status": "completed", "scores": data.get("scores", data)}
```

- [ ] **Step 4: Wire endpoint as non-blocking background entrypoint**

Modify `agent_service/main.py`:

```python
from agent_service.evaluation.judge import judge_answer
```

Add endpoint:

```python
@app.post("/internal/agent/evaluate")
async def evaluate(
    body: dict,
    _: None = Depends(require_internal_key),
) -> dict:
    result = await judge_answer(
        question=body.get("question", ""),
        answer=body.get("answer", ""),
        sources=body.get("sources", []),
        trace=body.get("trace", {}),
        graph_version=body.get("graph_version", settings.AGENT_GRAPH_VERSION),
        prompt_version=body.get("prompt_version", settings.AGENT_PROMPT_VERSION),
        model_name=body.get("model_name", settings.GEMINI_JUDGE_MODEL),
    )
    return result
```

- [ ] **Step 5: Run evaluation tests**

Run:

```powershell
pytest backend\tests\test_agent_evaluation.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit evaluation system**

Run:

```powershell
git add agent_service\evaluation agent_service\main.py backend\tests\test_agent_evaluation.py
git commit -m "feat: add async llm judge evaluation"
```

Expected: commit succeeds.

---

### Task 10: Admin Observability APIs

**Files:**
- Create: `backend/app/schemas/admin.py`
- Create: `backend/app/routers/admin.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_admin_observability.py`

- [ ] **Step 1: Write failing tests for admin role check helper**

Create `backend/tests/test_admin_observability.py`:

```python
import pytest
from fastapi import HTTPException

from app.routers.admin import require_admin_user


class FakeUser:
    def __init__(self, is_admin=False):
        self.is_admin = is_admin


def test_require_admin_accepts_admin_user():
    user = FakeUser(is_admin=True)

    assert require_admin_user(user) is user


def test_require_admin_rejects_non_admin_user():
    user = FakeUser(is_admin=False)

    with pytest.raises(HTTPException) as exc:
        require_admin_user(user)

    assert exc.value.status_code == 403
```

- [ ] **Step 2: Run admin tests and verify they fail**

Run:

```powershell
pytest backend\tests\test_admin_observability.py -q
```

Expected: FAIL because `app.routers.admin` does not exist.

- [ ] **Step 3: Add admin flag to user model**

Modify `backend/app/models/user.py` by adding a column to `User`:

```python
    is_admin = Column(Boolean, default=False, nullable=False)
```

Add an Alembic migration in a follow-up migration file if this column does not exist in the current schema:

```python
"""add user is_admin

Revision ID: 20260603_0011
Revises: 20260603_0010
Create Date: 2026-06-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260603_0011"
down_revision = "20260603_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "is_admin")
```

- [ ] **Step 4: Create admin schemas**

Create `backend/app/schemas/admin.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AgentTraceListItem(BaseModel):
    request_id: str
    session_id: str | None = None
    user_id: int | None = None
    intent: str | None = None
    agents_used: list[str]
    latency_ms: float
    status: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class AgentTraceDetail(BaseModel):
    request_id: str
    trace_summary_json: dict[str, Any]
    full_trace_json: dict[str, Any]
    readiness_json: dict[str, Any]
    status: str
    error_message: str | None = None

    class Config:
        from_attributes = True
```

- [ ] **Step 5: Create admin router**

Create `backend/app/routers/admin.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_observability import AgentTrace, EvalRun
from app.models.preference import ChatFeedback, MemoryProposal
from app.models.source_readiness import SourceReadiness
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.admin import AgentTraceDetail, AgentTraceListItem


router = APIRouter(prefix="/admin", tags=["Admin"])


def require_admin_user(user: User = Depends(get_current_user)) -> User:
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/chat-traces", response_model=list[AgentTraceListItem])
async def list_chat_traces(
    _: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    result = await db.execute(select(AgentTrace).order_by(desc(AgentTrace.created_at)).limit(limit))
    return list(result.scalars().all())


@router.get("/chat-traces/{request_id}", response_model=AgentTraceDetail)
async def get_chat_trace(
    request_id: str,
    _: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AgentTrace).where(AgentTrace.request_id == request_id))
    trace = result.scalar_one_or_none()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


@router.get("/pipeline-readiness")
async def pipeline_readiness(
    _: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SourceReadiness).order_by(SourceReadiness.source_name))
    return {"items": [row.__dict__ for row in result.scalars().all()]}


@router.get("/eval-runs")
async def eval_runs(
    _: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    result = await db.execute(select(EvalRun).order_by(desc(EvalRun.created_at)).limit(limit))
    return {"items": [row.__dict__ for row in result.scalars().all()]}


@router.get("/agent-health")
async def agent_health(
    _: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentTrace.status, func.count(), func.avg(AgentTrace.latency_ms)).group_by(AgentTrace.status)
    )
    return {
        "items": [
            {"status": status, "count": count, "avg_latency_ms": float(avg or 0)}
            for status, count, avg in result.all()
        ]
    }


@router.get("/top-queries")
async def top_queries(_: User = Depends(require_admin_user)):
    return {"items": []}


@router.get("/feedback")
async def feedback(
    _: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    result = await db.execute(select(ChatFeedback).order_by(desc(ChatFeedback.created_at)).limit(limit))
    return {"items": [row.__dict__ for row in result.scalars().all()]}


@router.get("/memory-proposals")
async def memory_proposals(
    _: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    result = await db.execute(select(MemoryProposal).order_by(desc(MemoryProposal.created_at)).limit(limit))
    return {"items": [row.__dict__ for row in result.scalars().all()]}
```

- [ ] **Step 6: Include admin router**

Modify `backend/app/main.py` imports:

```python
from app.routers import admin, auth, chat, listings, market, metrics, preferences
```

Add:

```python
app.include_router(admin.router, prefix="/api/v1")
```

- [ ] **Step 7: Run admin tests**

Run:

```powershell
pytest backend\tests\test_admin_observability.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit admin APIs**

Run:

```powershell
git add backend\app\schemas\admin.py backend\app\routers\admin.py backend\app\models\user.py backend\app\main.py backend\alembic\versions\20260603_0011_add_user_is_admin.py backend\tests\test_admin_observability.py
git commit -m "feat: add admin observability APIs"
```

Expected: commit succeeds.

---

### Task 11: Frontend ChatWidget Trace, Feedback, Memory Hints, And Admin Page

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/chatbot/ChatWidget.tsx`
- Create: `frontend/app/admin/page.tsx`
- Create: `frontend/components/admin/AdminDashboard.tsx`
- Test: frontend lint/build command

- [ ] **Step 1: Extend frontend types**

Modify `frontend/lib/types.ts` chat types:

```typescript
export interface TraceSummary {
  intent: string;
  agents: string[];
  source_count: number;
  latency_ms: number;
  warnings: string[];
}

export interface MemoryHint {
  action: string;
  key: string;
  value: unknown;
  confidence: number;
  evidence: string;
  requires_user_confirmation: boolean;
}

export interface ChatMessageResponse {
  session_id: string;
  role: string;
  content: string;
  agent_used: string | null;
  agents_used: string[];
  sources: ChatSource[] | null;
  suggested_actions: string[] | null;
  trace_summary: TraceSummary | null;
  memory_hints: MemoryHint[] | null;
  feedback_id: string | null;
  request_id: string | null;
  created_at: string | null;
}

export interface ChatFeedbackRequest {
  session_id: string;
  request_id: string;
  rating: "up" | "down";
  issue_type?: string;
  comment?: string;
}

export interface AdminTraceListItem {
  request_id: string;
  session_id: string | null;
  user_id: number | null;
  intent: string | null;
  agents_used: string[];
  latency_ms: number;
  status: string;
  created_at: string | null;
}
```

- [ ] **Step 2: Add frontend API functions**

Modify `frontend/lib/api.ts`:

```typescript
import type {
  AdminTraceListItem,
  ChatFeedbackRequest,
  // keep existing imports
} from "./types";
```

Add:

```typescript
function authHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function sendChatFeedback(body: ChatFeedbackRequest): Promise<{ id: number }> {
  return fetchJSON(`${BASE}/chat/feedback`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
}

export async function getAdminChatTraces(): Promise<AdminTraceListItem[]> {
  return fetchJSON(`${BASE}/admin/chat-traces`, {
    headers: authHeaders(),
  });
}

export async function getAdminPipelineReadiness(): Promise<{ items: Record<string, unknown>[] }> {
  return fetchJSON(`${BASE}/admin/pipeline-readiness`, {
    headers: authHeaders(),
  });
}
```

- [ ] **Step 3: Update ChatWidget message state**

Modify `frontend/components/chatbot/ChatWidget.tsx` `Message` interface:

```typescript
interface Message {
  role: "user" | "assistant";
  content: string;
  agent_used?: string | null;
  agents_used?: string[];
  sources?: ChatSource[] | null;
  suggested_actions?: string[] | null;
  trace_summary?: ChatMessageResponse["trace_summary"];
  memory_hints?: ChatMessageResponse["memory_hints"];
  request_id?: string | null;
}
```

When appending assistant response, include:

```typescript
          agents_used: res.agents_used,
          trace_summary: res.trace_summary,
          memory_hints: res.memory_hints,
          request_id: res.request_id,
```

Update `getAgentLabels` to prefer array:

```typescript
  const getAgentLabels = (msg: Message) => {
    const agents = msg.agents_used?.length
      ? msg.agents_used
      : (msg.agent_used || "").split(",").map((agent) => agent.trim());
    return agents
      .filter((agent) => agent && agent !== "none" && agent !== "bootstrap")
      .map((agent) => agentLabels[agent] || agent);
  };
```

Replace calls:

```tsx
{getAgentLabels(msg).length > 0 && (
  <div className="mb-1 flex flex-wrap gap-1">
    {getAgentLabels(msg).map((label) => (
      <span key={label} className="inline-block rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
        {label}
      </span>
    ))}
  </div>
)}
```

Add trace summary block below message content:

```tsx
{msg.trace_summary && (
  <div className="mt-2 rounded-md border border-border/70 bg-card/60 px-2 py-1 text-[11px] text-muted-foreground">
    <span>{msg.trace_summary.intent}</span>
    <span className="mx-1">·</span>
    <span>{msg.trace_summary.source_count} nguồn</span>
    <span className="mx-1">·</span>
    <span>{Math.round(msg.trace_summary.latency_ms)}ms</span>
  </div>
)}
```

Add memory hint block:

```tsx
{msg.memory_hints && msg.memory_hints.length > 0 && (
  <div className="mt-2 space-y-1">
    {msg.memory_hints.slice(0, 2).map((hint, index) => (
      <div key={`${hint.key}-${index}`} className="rounded-md border border-primary/20 bg-primary/5 px-2 py-1 text-[11px]">
        Lưu gợi ý {hint.key}: {String(hint.value)}
      </div>
    ))}
  </div>
)}
```

- [ ] **Step 4: Create admin dashboard component**

Create `frontend/components/admin/AdminDashboard.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { Activity, Database, MessageSquare, ShieldCheck } from "lucide-react";
import { getAdminChatTraces, getAdminPipelineReadiness } from "@/lib/api";
import type { AdminTraceListItem } from "@/lib/types";

export default function AdminDashboard() {
  const [traces, setTraces] = useState<AdminTraceListItem[]>([]);
  const [readiness, setReadiness] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [traceData, readinessData] = await Promise.all([
          getAdminChatTraces(),
          getAdminPipelineReadiness(),
        ]);
        setTraces(traceData);
        setReadiness(readinessData.items);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Khong tai duoc admin data");
      }
    }
    load();
  }, []);

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Agent Admin</h1>
          <p className="text-sm text-muted-foreground">Trace, readiness va chat quality dashboard</p>
        </div>
        <ShieldCheck className="text-primary" size={24} />
      </div>

      {error && <div className="mb-4 rounded-md border border-destructive/30 p-3 text-sm text-destructive">{error}</div>}

      <div className="grid gap-4 md:grid-cols-3">
        <section className="rounded-lg border border-border bg-card p-4">
          <div className="mb-2 flex items-center gap-2">
            <MessageSquare size={18} />
            <h2 className="font-medium">Chat Traces</h2>
          </div>
          <p className="text-2xl font-semibold">{traces.length}</p>
        </section>
        <section className="rounded-lg border border-border bg-card p-4">
          <div className="mb-2 flex items-center gap-2">
            <Database size={18} />
            <h2 className="font-medium">Readiness Sources</h2>
          </div>
          <p className="text-2xl font-semibold">{readiness.length}</p>
        </section>
        <section className="rounded-lg border border-border bg-card p-4">
          <div className="mb-2 flex items-center gap-2">
            <Activity size={18} />
            <h2 className="font-medium">Avg Latency</h2>
          </div>
          <p className="text-2xl font-semibold">
            {traces.length
              ? Math.round(traces.reduce((sum, trace) => sum + trace.latency_ms, 0) / traces.length)
              : 0}
            ms
          </p>
        </section>
      </div>

      <section className="mt-6 rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3 font-medium">Recent Traces</div>
        <div className="divide-y divide-border">
          {traces.slice(0, 20).map((trace) => (
            <div key={trace.request_id} className="grid gap-2 px-4 py-3 text-sm md:grid-cols-[1fr_140px_100px_100px]">
              <span className="truncate">{trace.request_id}</span>
              <span>{trace.intent || "unknown"}</span>
              <span>{Math.round(trace.latency_ms)}ms</span>
              <span>{trace.status}</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
```

- [ ] **Step 5: Create admin page**

Create `frontend/app/admin/page.tsx`:

```tsx
import AdminDashboard from "@/components/admin/AdminDashboard";

export default function AdminPage() {
  return <AdminDashboard />;
}
```

- [ ] **Step 6: Run frontend lint/build**

Run:

```powershell
cd frontend
npm run lint
npm run build
```

Expected: lint and build complete without TypeScript errors.

- [ ] **Step 7: Commit frontend upgrades**

Run:

```powershell
git add frontend\lib\types.ts frontend\lib\api.ts frontend\components\chatbot\ChatWidget.tsx frontend\app\admin\page.tsx frontend\components\admin\AdminDashboard.tsx
git commit -m "feat: add chat trace UI and admin dashboard"
```

Expected: commit succeeds.

---

### Task 12: Docker Compose And Deploy Readiness

**Files:**
- Modify: `docker-compose.yml`
- Create or Modify: `.env.example`
- Create: `docs/deploy/google-cloud-vm.md`
- Test: `backend/tests/test_agent_service_docker_config.py`

- [ ] **Step 1: Write failing Docker config test**

Create `backend/tests/test_agent_service_docker_config.py`:

```python
from pathlib import Path


def test_docker_compose_contains_agent_service():
    compose = Path("docker-compose.yml").read_text()

    assert "agent-service:" in compose
    assert "AGENT_INTERNAL_KEY" in compose
    assert "8100:8100" not in compose
    assert "http://agent-service:8100" in compose


def test_agent_service_dockerfile_exists():
    assert Path("agent_service/Dockerfile").exists()
    assert Path("agent_service/requirements.txt").exists()
```

- [ ] **Step 2: Run Docker config test and verify it fails**

Run:

```powershell
pytest backend\tests\test_agent_service_docker_config.py -q
```

Expected: FAIL because compose does not contain `agent-service`.

- [ ] **Step 3: Add `agent-service` to Docker Compose**

Modify `docker-compose.yml` between backend and frontend:

```yaml
  agent-service:
    build:
      context: .
      dockerfile: agent_service/Dockerfile
    container_name: realestate_agent_service
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-admin}:${POSTGRES_PASSWORD:-realestate_secret_2026}@postgres:5432/${POSTGRES_DB:-realestate}
      REDIS_URL: redis://redis:6379/0
      AGENT_INTERNAL_KEY: ${AGENT_INTERNAL_KEY:-dev-agent-internal-key}
      GEMINI_API_KEY: ${GEMINI_API_KEY:-}
      GEMINI_MODEL: ${GEMINI_MODEL:-gemini-2.0-flash}
      GEMINI_JUDGE_MODEL: ${GEMINI_JUDGE_MODEL:-gemini-2.0-flash}
    volumes:
      - ./agent_service:/app/agent_service
      - ./backend:/app/backend
      - ./data:/app/data
    command: uvicorn agent_service.main:app --host 0.0.0.0 --port 8100 --reload
    healthcheck:
      test: ["CMD-SHELL", "curl -f -H \"X-Internal-Agent-Key: ${AGENT_INTERNAL_KEY:-dev-agent-internal-key}\" http://localhost:8100/internal/agent/health"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 30s
```

Modify backend environment:

```yaml
      AGENT_SERVICE_URL: http://agent-service:8100
      AGENT_INTERNAL_KEY: ${AGENT_INTERNAL_KEY:-dev-agent-internal-key}
      CHATBOT_AGENT_SERVICE_ENABLED: ${CHATBOT_AGENT_SERVICE_ENABLED:-false}
```

Modify backend `depends_on`:

```yaml
      agent-service:
        condition: service_healthy
```

- [ ] **Step 4: Create `.env.example`**

Create `.env.example`:

```text
POSTGRES_DB=realestate
POSTGRES_USER=admin
POSTGRES_PASSWORD=change-me
POSTGRES_PORT=5432

DATABASE_URL=postgresql+asyncpg://admin:change-me@postgres:5432/realestate
REDIS_URL=redis://redis:6379/0

JWT_SECRET_KEY=change-me-long-random-secret
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
CORS_ORIGINS=http://localhost:3000

GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
GEMINI_JUDGE_MODEL=gemini-2.0-flash
HF_EMBEDDING_MODEL=BAAI/bge-m3
COHERE_API_KEY=

AGENT_SERVICE_URL=http://agent-service:8100
AGENT_INTERNAL_KEY=change-me-internal-agent-key
CHATBOT_AGENT_SERVICE_ENABLED=false
CHATBOT_LLM_JUDGE_ENABLED=false
CHATBOT_MEMORY_ENABLED=true
CHATBOT_ADMIN_ENABLED=true
CHATBOT_TRACE_LEVEL=full

ANON_CHAT_DAILY_LIMIT=20
AUTH_CHAT_DAILY_LIMIT=200

NEXT_PUBLIC_API_URL=/api/v1
INTERNAL_API_URL=http://backend:8000
```

- [ ] **Step 5: Create Google Cloud VM deploy guide**

Create `docs/deploy/google-cloud-vm.md`:

```markdown
# Google Cloud VM Deployment

## Target

Run the feature-complete real-estate app on a Google Cloud Compute Engine VM using Docker Compose.

## VM

- Ubuntu LTS
- 2 vCPU minimum for a small demo
- 8 GB RAM recommended because BGE-M3/sentence-transformers can be memory-heavy
- 50 GB disk minimum

## Setup

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin git
sudo usermod -aG docker "$USER"
```

Log out and back in after adding the Docker group.

## Configure

```bash
git clone https://github.com/trunghieunef/chatbot_bds.git
cd chatbot_bds
cp .env.example .env
nano .env
```

Set strong values for:

- `POSTGRES_PASSWORD`
- `JWT_SECRET_KEY`
- `AGENT_INTERNAL_KEY`
- `GEMINI_API_KEY`

## Start

```bash
docker compose up -d --build postgres redis
docker compose up -d --build agent-service backend frontend
```

## Smoke Tests

```bash
curl http://localhost:8000/api/v1/health
curl -H "X-Internal-Agent-Key: $AGENT_INTERNAL_KEY" http://localhost:8100/internal/agent/health
curl http://localhost:3000
```

## Enable Agent Service

After health checks pass, set:

```text
CHATBOT_AGENT_SERVICE_ENABLED=true
```

Then restart:

```bash
docker compose up -d backend
```

## Backup

```bash
docker exec realestate_postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql
```
```

- [ ] **Step 6: Run Docker config tests**

Run:

```powershell
pytest backend\tests\test_agent_service_docker_config.py -q
docker compose config
```

Expected: tests PASS and `docker compose config` exits successfully.

- [ ] **Step 7: Commit deploy readiness**

Run:

```powershell
git add docker-compose.yml .env.example docs\deploy\google-cloud-vm.md backend\tests\test_agent_service_docker_config.py
git commit -m "feat: add agent service docker deployment"
```

Expected: commit succeeds.

---

### Task 13: Final Verification And Documentation Cleanup

**Files:**
- Modify: `docs/multiagent-workflow.md`
- Modify: `docs/pipeline.md`
- Modify: `docs/implementation_plan.md`
- Modify: docs references to root-level `chatbot/` scaffold; do not delete scaffold code in this plan

- [ ] **Step 1: Update multi-agent workflow docs**

Modify `docs/multiagent-workflow.md` to start with:

```markdown
# Multi-Agent Chatbot Workflow

The production chatbot uses the public backend `/api/v1/chat` endpoint as the only frontend entrypoint. The backend owns auth, chat sessions, chat messages, user preferences, quota, and public API contracts. When `CHATBOT_AGENT_SERVICE_ENABLED=true`, the backend calls the internal Agent Service at `POST /internal/agent/chat`.

The internal Agent Service owns LangGraph orchestration, Gemini routing/reasoning/synthesis, RAG retrieval planning, trace generation, async evaluation, and memory proposals. The root-level `chatbot/` package is legacy scaffold code. This plan updates documentation references but does not delete that package.
```

- [ ] **Step 2: Update pipeline docs**

Modify `docs/pipeline.md` source-flow note to include:

```markdown
Chatbot retrieval reads indexed `chunks` through the internal Agent Service tools. Web/API visibility still depends on parent tables (`listings`, `projects`, `articles`) and must not be blocked by embedding/index failures. Agent readiness surfaces missing parent/chunk data in admin views and chat trace warnings.
```

- [ ] **Step 3: Run complete backend verification**

Run:

```powershell
pytest backend\tests -q
python -m compileall backend\app agent_service data_pipeline chatbot crawler
```

Expected: all tests PASS and compileall PASS.

- [ ] **Step 4: Run frontend verification**

Run:

```powershell
cd frontend
npm run lint
npm run build
```

Expected: lint and build PASS.

- [ ] **Step 5: Run Docker verification**

Run:

```powershell
docker compose config
```

Expected: command exits successfully.

- [ ] **Step 6: Commit docs and final cleanup**

Run:

```powershell
git add docs\multiagent-workflow.md docs\pipeline.md docs\implementation_plan.md
git commit -m "docs: update agent platform chatbot workflow"
```

Expected: commit succeeds.

---

## Verification Matrix

Run these after the full plan is implemented:

```powershell
pytest backend\tests -q
python -m compileall backend\app agent_service data_pipeline chatbot crawler
cd frontend
npm run lint
npm run build
cd ..
docker compose config
```

Expected:

- pytest passes;
- compileall passes;
- frontend lint/build passes;
- Docker Compose config renders successfully;
- `/api/v1/chat` works with `CHATBOT_AGENT_SERVICE_ENABLED=false`;
- `/api/v1/chat` works with `CHATBOT_AGENT_SERVICE_ENABLED=true` when agent-service is healthy;
- `/internal/agent/health` rejects missing internal key and accepts the correct key;
- admin APIs reject non-admin users;
- ChatWidget shows answer, sources, trace summary, and memory hints when present.

## Rollback Strategy

Keep `CHATBOT_AGENT_SERVICE_ENABLED=false` as the default until the Agent Service passes smoke tests. If the internal service fails in a deployment, set this flag to `false` and restart the backend. The legacy production chatbot pipeline remains the fallback path during the migration.

## Self-Review Notes

- Spec coverage: This plan covers internal Agent Service, LangGraph, Gemini-ready agent interfaces, multi-source RAG tools, memory proposals, evaluation, admin APIs, frontend trace/admin UI, Docker Compose, and deploy docs.
- Scope boundary: Public web search, streaming, managed cloud database split, and fine-tuning remain outside this implementation plan.
- Version tracking: Evaluation and trace models include graph, prompt, and model fields.
- Ownership: Backend owns preferences and public chat persistence; Agent Service only returns memory proposals and traces.
