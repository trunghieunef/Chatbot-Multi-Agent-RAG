import asyncio
import uuid
from datetime import datetime

from app.routers import chat
from app.schemas.chat import ChatMessageRequest
from app.services.agent_service.contracts import (
    AgentChatResponse,
    MemoryProposal,
    TraceSummary,
)


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


class FakeAgentClient:
    def __init__(self):
        self.request = None

    async def chat(self, request):
        self.request = request
        return AgentChatResponse(
            request_id=request.request_id,
            final_response="Agent answer",
            agents_used=["router", "property_search"],
            sources=[{"type": "listing", "product_id": "hf-1"}],
            suggested_actions=["Compare"],
            trace_summary=TraceSummary(
                intent="property_search",
                agents=["router", "property_search"],
                source_count=1,
                latency_ms=12.5,
            ),
            full_trace={"nodes": ["router", "property_search"]},
            memory_proposals=[
                MemoryProposal(
                    action="upsert",
                    key="budget",
                    value={"max": 3000000000},
                    confidence=0.8,
                    evidence="User mentioned budget",
                    requires_user_confirmation=True,
                )
            ],
            readiness={"listings": "ready"},
            evaluation_candidate={"quality": "candidate"},
        )


def test_feature_flag_enabled_calls_internal_agent_service(monkeypatch):
    fake_client = FakeAgentClient()
    context = [{"role": "user", "content": "Earlier", "created_at": None, "sources": []}]

    monkeypatch.setattr(chat, "is_agent_service_enabled", lambda: True)
    monkeypatch.setattr(chat, "get_agent_service_client", lambda: fake_client)
    monkeypatch.setattr(chat, "build_conversation_context", lambda db, session_id: context)
    monkeypatch.setattr(chat, "load_user_preferences", lambda db, user_id: {"city": "HCMC"})
    monkeypatch.setattr(chat, "persist_agent_observability", lambda *args: None)
    monkeypatch.setattr(chat, "handle_memory_proposals", lambda *args: [{"key": "budget"}])

    response = asyncio.run(
        chat.send_message(
            ChatMessageRequest(message="Tim nha Quan 2"),
            user=None,
            db=FakeDB(),
        )
    )

    assert response.content == "Agent answer"
    assert response.agents_used == ["router", "property_search"]
    assert response.trace_summary["intent"] == "property_search"
    assert response.memory_hints == [{"key": "budget"}]
    assert response.request_id
    assert fake_client.request.message == "Tim nha Quan 2"
    assert [
        item.model_dump(mode="json")
        for item in fake_client.request.conversation_context
    ] == context
    assert fake_client.request.user_preferences == {"city": "HCMC"}


def test_feature_flag_disabled_falls_back_to_existing_backend_pipeline(monkeypatch):
    called = {}

    async def fake_pipeline(message, db, session_id):
        called["message"] = message
        called["session_id"] = session_id
        return {
            "final_response": "Legacy answer",
            "agent_used": "market_analysis, property_search",
            "sources": [{"product_id": "hf-2"}],
            "suggested_actions": ["Schedule viewing"],
        }

    monkeypatch.setattr(chat, "is_agent_service_enabled", lambda: False)
    monkeypatch.setattr(chat, "_run_chatbot_pipeline", fake_pipeline)
    monkeypatch.setattr(chat, "persist_agent_observability", lambda *args: None)
    monkeypatch.setattr(chat, "handle_memory_proposals", lambda *args: [])

    response = asyncio.run(
        chat.send_message(
            ChatMessageRequest(message="Phan tich thi truong"),
            user=None,
            db=FakeDB(),
        )
    )

    assert called["message"] == "Phan tich thi truong"
    assert response.content == "Legacy answer"
    assert response.agent_used == "market_analysis, property_search"
    assert response.agents_used == ["market_analysis", "property_search"]
    assert response.trace_summary["intent"] == "legacy"
    assert response.sources == [{"product_id": "hf-2"}]
