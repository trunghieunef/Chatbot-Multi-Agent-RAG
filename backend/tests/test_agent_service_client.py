import json
import traceback

import httpx
import pytest

from app.config import Settings
from app.services.agent_service.client import AgentServiceClient, AgentServiceError
from app.services.agent_service.contracts import AgentChatRequest


AGENT_SERVICE_SETTING_ENV_VARS = (
    "AGENT_SERVICE_URL",
    "AGENT_INTERNAL_KEY",
    "AGENT_SERVICE_TIMEOUT_SECONDS",
    "CHATBOT_AGENT_SERVICE_ENABLED",
    "CHATBOT_LLM_JUDGE_ENABLED",
    "CHATBOT_MEMORY_ENABLED",
    "CHATBOT_ADMIN_ENABLED",
    "CHATBOT_TRACE_LEVEL",
    "GEMINI_JUDGE_MODEL",
    "ANON_CHAT_DAILY_LIMIT",
    "AUTH_CHAT_DAILY_LIMIT",
)


def _format_exception(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def test_agent_service_settings_defaults(monkeypatch):
    for env_var in AGENT_SERVICE_SETTING_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)

    settings = Settings(_env_file=None)

    assert settings.AGENT_SERVICE_URL == "http://localhost:8100"
    assert settings.AGENT_INTERNAL_KEY == "dev-agent-internal-key"
    assert settings.AGENT_SERVICE_TIMEOUT_SECONDS == 45.0
    assert settings.CHATBOT_AGENT_SERVICE_ENABLED is True
    assert settings.CHATBOT_LLM_JUDGE_ENABLED is False
    assert settings.CHATBOT_MEMORY_ENABLED is True
    assert settings.CHATBOT_ADMIN_ENABLED is True
    assert settings.CHATBOT_TRACE_LEVEL == "full"
    assert settings.GEMINI_JUDGE_MODEL == "gemini-2.0-flash"
    assert settings.ANON_CHAT_DAILY_LIMIT == 20
    assert settings.AUTH_CHAT_DAILY_LIMIT == 200


@pytest.mark.asyncio
async def test_agent_service_client_sends_internal_key():
    seen_headers = {}
    seen_request = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["key"] = request.headers.get("X-Internal-Agent-Key")
        seen_request["path"] = request.url.path
        seen_request["body"] = json.loads(request.content.decode())
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
    assert seen_request["path"] == "/internal/agent/chat"
    assert seen_request["body"]["request_id"] == "req-1"
    assert response.final_response == "ok"
    assert response.agents_used == ["property_search"]


@pytest.mark.asyncio
async def test_agent_service_client_raises_safe_error_on_500():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={
                "detail": "boom",
                "internal_key": "secret",
                "payload": "customer-budget-7-ty",
            },
        )

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

    message = str(exc.value)
    assert message == "Agent Service request failed: HTTP 500"
    assert "secret" not in message
    assert "boom" not in message
    assert "customer-budget-7-ty" not in message
    assert "Tim nha" not in message
    assert exc.value.__cause__ is None

    formatted = _format_exception(exc.value)
    assert "secret" not in formatted
    assert "boom" not in formatted
    assert "customer-budget-7-ty" not in formatted
    assert "Tim nha" not in formatted


@pytest.mark.asyncio
async def test_agent_service_client_raises_safe_error_on_invalid_response():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "request_id": "req-1",
                "user_message": "Tim nha gan song cho gia dinh toi",
                "trace": {"memory_proposal": "budget-secret-9-ty"},
            },
        )

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

    message = str(exc.value)
    assert message == "Agent Service request failed: invalid response"
    assert "Tim nha" not in message
    assert "gan song" not in message
    assert "budget-secret-9-ty" not in message
    assert "secret" not in message
    assert exc.value.__cause__ is None

    formatted = _format_exception(exc.value)
    assert "Tim nha" not in formatted
    assert "gan song" not in formatted
    assert "budget-secret-9-ty" not in formatted
    assert "secret" not in formatted
