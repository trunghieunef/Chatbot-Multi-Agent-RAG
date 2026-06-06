import asyncio
import uuid
from datetime import datetime

from app.routers import chat
from app.schemas.chat import ChatMessageRequest


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


def test_send_message_uses_multi_agent_pipeline_by_default(monkeypatch):
    called = {}

    async def fake_multi_agent(message, db, session_id=None):
        called["message"] = message
        called["session_id"] = session_id
        return {
            "final_response": "Multi-agent response",
            "agent_used": "market_analysis, property_search",
            "sources": [{"product_id": "hf-1"}],
            "suggested_actions": ["Compare"],
        }

    monkeypatch.setattr(chat, "is_agent_service_enabled", lambda: False)
    monkeypatch.setattr(chat, "run_chat_pipeline", fake_multi_agent, raising=False)

    response = asyncio.run(
        chat.send_message(
            ChatMessageRequest(message="Tim nha va xem thi truong"),
            user=None,
            db=FakeDB(),
        )
    )

    assert called["message"] == "Tim nha va xem thi truong"
    assert response.content == "Multi-agent response"
    assert response.agent_used == "market_analysis, property_search"
    assert response.sources == [{"product_id": "hf-1"}]
    assert response.suggested_actions == ["Compare"]


def test_send_message_returns_safe_error_when_multi_agent_fails(monkeypatch):
    async def failing_multi_agent(message, db, session_id=None):
        raise RuntimeError("multi-agent unavailable")

    monkeypatch.setattr(chat, "is_agent_service_enabled", lambda: False)
    monkeypatch.setattr(chat, "run_chat_pipeline", failing_multi_agent, raising=False)

    response = asyncio.run(
        chat.send_message(
            ChatMessageRequest(message="Tim nha"),
            user=None,
            db=FakeDB(),
        )
    )

    assert "chua san sang" in response.content
    assert response.agent_used == "multi_agent_error"
    assert response.sources == []
    assert response.suggested_actions


def test_send_message_does_not_call_simple_rag(monkeypatch):
    async def failing_multi_agent(message, db, session_id=None):
        raise ValueError("multi-agent unavailable")

    monkeypatch.setattr(chat, "is_agent_service_enabled", lambda: False)
    monkeypatch.setattr(chat, "run_chat_pipeline", failing_multi_agent, raising=False)
    assert not hasattr(chat, "run_simple_rag")

    response = asyncio.run(
        chat.send_message(
            ChatMessageRequest(message="Tim nha"),
            user=None,
            db=FakeDB(),
        )
    )

    assert response.agent_used == "multi_agent_error"
    assert response.sources == []
    assert response.suggested_actions
