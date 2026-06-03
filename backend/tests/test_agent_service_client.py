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
