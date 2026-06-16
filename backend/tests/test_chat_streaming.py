from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from app.routers import chat
from app.services.agent_service.contracts import AgentChatResponse, TraceSummary
from app.schemas.chat import ChatMessageRequest


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, query):
        return type("Result", (), {"scalar_one_or_none": lambda self: None})()

    async def flush(self):
        for obj in self.added:
            if obj.__class__.__name__ == "ChatSession" and obj.id is None:
                obj.id = uuid.uuid4()
            if obj.__class__.__name__ == "ChatSession" and obj.created_at is None:
                obj.created_at = datetime(2026, 1, 1)


@pytest.mark.asyncio
async def test_format_sse_serializes_named_event():
    payload = chat._format_sse(
        {"event": "started", "request_id": "req-stream", "payload": {}}
    )

    assert payload.startswith("event: started\n")
    assert '"request_id": "req-stream"' in payload
    assert payload.endswith("\n\n")


@pytest.mark.asyncio
async def test_stream_message_returns_sse_response(monkeypatch):
    async def fake_stream_response(*args, **kwargs):
        yield {"event": "started", "request_id": "req-stream", "payload": {}}
        yield {
            "event": "final",
            "request_id": "req-stream",
            "payload": {"content": "Xin chao"},
        }

    monkeypatch.setattr(chat, "_enforce_chat_abuse_guard", lambda *args, **kwargs: None)

    async def fake_quota(*args, **kwargs):
        return None

    monkeypatch.setattr(chat, "enforce_chat_quota", fake_quota)
    monkeypatch.setattr(chat, "_stream_agent_service_pipeline", fake_stream_response, raising=False)

    response = await chat.stream_message(
        ChatMessageRequest(message="Xin chao"),
        user=None,
        db=FakeDB(),
    )
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    body = "".join(chunks)

    assert response.media_type == "text/event-stream"
    assert "event: started" in body
    assert "event: final" in body
    assert json.loads(body.split("data: ")[1].split("\n\n")[0])["event"] == "started"


@pytest.mark.asyncio
async def test_stream_message_persists_chat_exchange(monkeypatch):
    async def fake_agent_response(*args, **kwargs):
        return AgentChatResponse(
            request_id="req-stream-persist",
            final_response="Xin chao tu agent",
            agents_used=["property_search"],
            suggested_actions=["Compare"],
            trace_summary=TraceSummary(
                intent="property_search",
                agents=["property_search"],
            ),
            full_trace={"mode": "agent_service"},
        )

    monkeypatch.setattr(chat, "_enforce_chat_abuse_guard", lambda *args, **kwargs: None)

    async def fake_quota(*args, **kwargs):
        return None

    async def fake_observability(*args, **kwargs):
        return None

    monkeypatch.setattr(chat, "enforce_chat_quota", fake_quota)
    monkeypatch.setattr(chat, "_run_agent_service_pipeline", fake_agent_response)
    monkeypatch.setattr(chat, "persist_agent_observability", fake_observability)

    db = FakeDB()
    response = await chat.stream_message(
        ChatMessageRequest(message="Xin chao"),
        user=None,
        db=db,
    )
    async for _ in response.body_iterator:
        pass

    messages = [item for item in db.added if item.__class__.__name__ == "ChatMessage"]
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "Xin chao"
    assert messages[1].content == "Xin chao tu agent"
    assert messages[1].metadata_json["suggested_actions"] == ["Compare"]


@pytest.mark.asyncio
async def test_stream_message_emits_error_event_when_pipeline_fails(monkeypatch):
    async def failing_agent_response(*args, **kwargs):
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(chat, "_enforce_chat_abuse_guard", lambda *args, **kwargs: None)

    async def fake_quota(*args, **kwargs):
        return None

    monkeypatch.setattr(chat, "enforce_chat_quota", fake_quota)
    monkeypatch.setattr(chat, "_run_agent_service_pipeline", failing_agent_response)

    response = await chat.stream_message(
        ChatMessageRequest(message="Xin chao"),
        user=None,
        db=FakeDB(),
    )
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    body = "".join(chunks)

    assert "event: started" in body
    assert "event: error" in body
    error_payload = json.loads(body.split("event: error\n")[1].split("data: ")[1].split("\n\n")[0])
    assert error_payload["event"] == "error"
    assert error_payload["payload"]["code"] == "stream_pipeline_error"


@pytest.mark.asyncio
async def test_stream_message_final_payload_includes_session_id(monkeypatch):
    async def fake_agent_response(*args, **kwargs):
        return AgentChatResponse(
            request_id="req-stream-session",
            final_response="Xin chao tu agent",
            agents_used=["property_search"],
            suggested_actions=["Compare"],
            trace_summary=TraceSummary(
                intent="property_search",
                agents=["property_search"],
            ),
            full_trace={"mode": "agent_service"},
        )

    monkeypatch.setattr(chat, "_enforce_chat_abuse_guard", lambda *args, **kwargs: None)

    async def fake_quota(*args, **kwargs):
        return None

    async def fake_observability(*args, **kwargs):
        return None

    monkeypatch.setattr(chat, "enforce_chat_quota", fake_quota)
    monkeypatch.setattr(chat, "_run_agent_service_pipeline", fake_agent_response)
    monkeypatch.setattr(chat, "persist_agent_observability", fake_observability)

    db = FakeDB()
    response = await chat.stream_message(
        ChatMessageRequest(message="Xin chao"),
        user=None,
        db=db,
    )
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    body = "".join(chunks)

    final_payload = json.loads(body.split("event: final\n")[1].split("data: ")[1].split("\n\n")[0])
    session = next(item for item in db.added if item.__class__.__name__ == "ChatSession")
    assert final_payload["payload"]["session_id"] == str(session.id)
