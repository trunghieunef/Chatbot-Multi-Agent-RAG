import asyncio
import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException

from app.routers import chat
from app.schemas.chat import ChatFeedbackRequest, ChatMessageRequest
from app.services.agent_service.contracts import (
    AgentChatResponse,
    MemoryProposal,
    TraceSummary,
)


class FakeDB:
    def __init__(self, session=None, messages=None, quota_count=0):
        self.added = []
        self.session = session
        self.messages = messages or []
        self.quota_count = quota_count
        self.execute_count = 0
        self.commit_count = 0

    def add(self, obj):
        self.added.append(obj)

    def _is_count_query(self, query):
        return "count(" in str(query).lower()

    async def execute(self, query, params=None):
        self.execute_count += 1
        if self._is_count_query(query):
            return SimpleNamespace(scalar=lambda: self.quota_count)
        if self.execute_count == 1:
            return SimpleNamespace(scalar_one_or_none=lambda: self.session)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self.messages))

    async def flush(self):
        for obj in self.added:
            if obj.__class__.__name__ == "ChatSession" and obj.id is None:
                obj.id = uuid.uuid4()
            if obj.__class__.__name__ == "ChatMessage" and obj.created_at is None:
                obj.created_at = datetime(2026, 1, 1)
            if obj.__class__.__name__ == "ChatFeedback" and obj.id is None:
                obj.id = len(
                    [
                        item
                        for item in self.added
                        if item.__class__.__name__ == "ChatFeedback"
                        and item.id is not None
                    ]
                ) + 1
            if obj.__class__.__name__ == "MemoryProposal" and obj.id is None:
                obj.id = len(
                    [
                        item
                        for item in self.added
                        if item.__class__.__name__ == "MemoryProposal"
                        and item.id is not None
                    ]
                ) + 1

    async def commit(self):
        self.commit_count += 1


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

    async def memory_hints(*args):
        return [{"key": "budget"}]

    monkeypatch.setattr(chat, "is_agent_service_enabled", lambda: True)
    monkeypatch.setattr(chat, "get_agent_service_client", lambda: fake_client)
    monkeypatch.setattr(chat, "build_conversation_context", lambda db, session_id: context)
    monkeypatch.setattr(chat, "load_user_preferences", lambda db, user_id: {"city": "HCMC"})
    monkeypatch.setattr(chat, "persist_agent_observability", lambda *args: None)
    monkeypatch.setattr(chat, "handle_memory_proposals", memory_hints)

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


def test_agent_response_accepts_extended_source_shape():
    response = AgentChatResponse(
        request_id="req-source-shape",
        final_response="Answer",
        agents_used=["property_search"],
        sources=[
            {
                "type": "listing",
                "domain": "property",
                "id": "listing:p-1",
                "product_id": "p-1",
                "title": "Can ho A",
                "url": None,
                "snippet": "Can ho A Quan 7",
                "location": {"district": "Quan 7"},
                "citation": None,
                "score": 0.91,
                "metadata": {"source_identity": "listing:p-1"},
            }
        ],
        trace_summary=TraceSummary(
            intent="property_search",
            agents=["property_search"],
            source_count=1,
            latency_ms=1,
            warnings=[
                {
                    "code": "investment_market_data_missing",
                    "domain": "market",
                    "message": "Market aggregate evidence is not available.",
                    "retryable": False,
                    "details": {},
                }
            ],
        ),
    )

    assert response.sources[0].id == "listing:p-1"
    assert response.sources[0].domain == "property"
    assert response.trace_summary.warnings[0].code == (
        "investment_market_data_missing"
    )


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

    async def memory_hints(*args):
        return []

    monkeypatch.setattr(chat, "is_agent_service_enabled", lambda: False)
    monkeypatch.setattr(chat, "_run_chatbot_pipeline", fake_pipeline)
    monkeypatch.setattr(chat, "persist_agent_observability", lambda *args: None)
    monkeypatch.setattr(chat, "handle_memory_proposals", memory_hints)

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


def test_authenticated_user_cannot_use_another_users_session(monkeypatch):
    session_id = uuid.uuid4()
    db = FakeDB(session=SimpleNamespace(id=session_id, user_id=7))

    async def fail_pipeline(*args):
        raise AssertionError("foreign session must not reach agent pipeline")

    monkeypatch.setattr(chat, "_run_agent_service_pipeline", fail_pipeline)

    try:
        asyncio.run(
            chat.send_message(
                ChatMessageRequest(message="Tim nha", session_id=session_id),
                user=SimpleNamespace(id=42),
                db=db,
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("expected session ownership rejection")

    assert db.added == []


def test_anonymous_user_cannot_use_authenticated_session(monkeypatch):
    session_id = uuid.uuid4()
    db = FakeDB(session=SimpleNamespace(id=session_id, user_id=7))

    async def fail_pipeline(*args):
        raise AssertionError("authenticated session must not reach agent pipeline")

    monkeypatch.setattr(chat, "_run_agent_service_pipeline", fail_pipeline)

    try:
        asyncio.run(
            chat.send_message(
                ChatMessageRequest(message="Tim nha", session_id=session_id),
                user=None,
                db=db,
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("expected session ownership rejection")

    assert db.added == []


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


def test_session_history_allows_authenticated_owner():
    session_id = uuid.uuid4()
    message = SimpleNamespace(
        role="user",
        content="Owner message",
        agent_used=None,
        metadata_json={},
        created_at=datetime(2026, 1, 1),
    )
    db = FakeDB(
        session=SimpleNamespace(
            id=session_id,
            user_id=42,
            title="owner",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        ),
        messages=[message],
    )

    response = asyncio.run(
        chat.get_session_history(
            session_id,
            user=SimpleNamespace(id=42),
            db=db,
        )
    )

    assert response.session.id == session_id
    assert response.session.message_count == 1
    assert response.messages[0].content == "Owner message"


def test_session_history_allows_anonymous_session_by_direct_id():
    session_id = uuid.uuid4()
    message = SimpleNamespace(
        role="assistant",
        content="Anonymous answer",
        agent_used="property_search",
        metadata_json={},
        created_at=datetime(2026, 1, 1),
    )
    db = FakeDB(
        session=SimpleNamespace(
            id=session_id,
            user_id=None,
            title="anonymous",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        ),
        messages=[message],
    )

    response = asyncio.run(
        chat.get_session_history(
            session_id,
            user=None,
            db=db,
        )
    )

    assert response.session.id == session_id
    assert response.session.message_count == 1
    assert response.messages[0].content == "Anonymous answer"


def test_agent_service_context_excludes_current_user_message(monkeypatch):
    fake_client = FakeAgentClient()

    def inspect_context(db, session_id):
        current_user_messages = [
            item
            for item in db.added
            if item.__class__.__name__ == "ChatMessage" and item.role == "user"
        ]
        assert current_user_messages == []
        return []

    async def memory_hints(*args):
        return []

    monkeypatch.setattr(chat, "is_agent_service_enabled", lambda: True)
    monkeypatch.setattr(chat, "get_agent_service_client", lambda: fake_client)
    monkeypatch.setattr(chat, "build_conversation_context", inspect_context)
    monkeypatch.setattr(chat, "load_user_preferences", lambda db, user_id: {})
    monkeypatch.setattr(chat, "persist_agent_observability", lambda *args: None)
    monkeypatch.setattr(chat, "handle_memory_proposals", memory_hints)

    response = asyncio.run(
        chat.send_message(
            ChatMessageRequest(message="Tin moi nhat"),
            user=None,
            db=FakeDB(),
        )
    )

    assert response.content == "Agent answer"


def test_observability_failure_does_not_fail_committed_chat_response(monkeypatch):
    db = FakeDB()
    fake_client = FakeAgentClient()

    async def memory_hints(*args):
        return []

    async def fail_observability(*args):
        raise RuntimeError("observability database unavailable")

    monkeypatch.setattr(chat, "is_agent_service_enabled", lambda: True)
    monkeypatch.setattr(chat, "get_agent_service_client", lambda: fake_client)
    monkeypatch.setattr(chat, "build_conversation_context", lambda db, session_id: [])
    monkeypatch.setattr(chat, "load_user_preferences", lambda db, user_id: {})
    monkeypatch.setattr(chat, "persist_agent_observability", fail_observability)
    monkeypatch.setattr(chat, "handle_memory_proposals", memory_hints)

    response = asyncio.run(
        chat.send_message(
            ChatMessageRequest(message="Tim nha Quan 2"),
            user=None,
            db=db,
        )
    )

    chat_messages = [
        item for item in db.added if item.__class__.__name__ == "ChatMessage"
    ]
    assert response.content == "Agent answer"
    assert [message.role for message in chat_messages] == ["user", "assistant"]
    assert db.commit_count == 1


def test_legacy_agent_shape_uses_safe_fallback_answer():
    response = chat._legacy_response_to_agent_shape(
        "req-legacy",
        {
            "agent_used": "",
            "sources": [],
            "suggested_actions": [],
        },
    )

    assert response.final_response == "Toi chua tao duoc cau tra loi phu hop."
    assert response.agents_used == ["unknown"]


def test_memory_proposals_store_value_wrapper_for_authenticated_user():
    db = FakeDB()
    session_id = uuid.uuid4()
    response = AgentChatResponse(
        request_id="req-memory",
        final_response="Agent answer",
        agents_used=["property_search"],
        sources=[],
        suggested_actions=[],
        trace_summary=TraceSummary(
            intent="property_search",
            agents=["property_search"],
            source_count=0,
            latency_ms=1,
        ),
        full_trace={},
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
    )

    hints = asyncio.run(
        chat.handle_memory_proposals(
            db,
            SimpleNamespace(id=session_id),
            SimpleNamespace(id=42),
            response,
        )
    )

    persisted = [
        item for item in db.added if item.__class__.__name__ == "MemoryProposal"
    ][0]
    assert persisted.value_json == {"value": {"max": 3000000000}}
    assert hints[0]["key"] == "budget"


def test_auto_applied_memory_proposal_creates_user_preference():
    db = FakeDB()
    session_id = uuid.uuid4()
    response = AgentChatResponse(
        request_id="req-memory-auto",
        final_response="Agent answer",
        agents_used=["property_search"],
        sources=[],
        suggested_actions=[],
        trace_summary=TraceSummary(
            intent="property_search",
            agents=["property_search"],
            source_count=0,
            latency_ms=1,
        ),
        full_trace={},
        memory_proposals=[
            MemoryProposal(
                action="upsert",
                key="preferred_city",
                value="Da Nang",
                confidence=0.9,
                evidence="User said they prefer Da Nang",
                requires_user_confirmation=False,
            )
        ],
    )

    hints = asyncio.run(
        chat.handle_memory_proposals(
            db,
            SimpleNamespace(id=session_id),
            SimpleNamespace(id=42),
            response,
        )
    )

    proposal = [
        item for item in db.added if item.__class__.__name__ == "MemoryProposal"
    ][0]
    preference = [
        item for item in db.added if item.__class__.__name__ == "UserPreference"
    ][0]
    assert proposal.status == "auto_applied"
    assert preference.user_id == 42
    assert preference.key == "preferred_city"
    assert preference.value_json == {"value": "Da Nang"}
    assert preference.confidence == 0.9
    assert preference.source == "agent_proposal"
    assert hints == []


def test_submit_feedback_persists_session_feedback():
    session_id = uuid.uuid4()
    db = FakeDB(session=SimpleNamespace(id=session_id, user_id=None))

    response = asyncio.run(
        chat.submit_feedback(
            ChatFeedbackRequest(
                session_id=session_id,
                request_id="req-feedback",
                rating="negative",
                issue_type="wrong_listing",
                comment="The recommendation missed my district.",
                metadata_json={"source": "chat_panel"},
            ),
            user=None,
            db=db,
        )
    )

    feedback = [
        item for item in db.added if item.__class__.__name__ == "ChatFeedback"
    ][0]
    assert response.id == 1
    assert feedback.user_id is None
    assert feedback.session_id == session_id
    assert feedback.request_id == "req-feedback"
    assert feedback.rating == "negative"
    assert feedback.issue_type == "wrong_listing"
    assert feedback.comment == "The recommendation missed my district."
    assert feedback.metadata_json == {"source": "chat_panel"}


def test_authenticated_user_cannot_submit_feedback_for_another_users_session():
    session_id = uuid.uuid4()
    db = FakeDB(session=SimpleNamespace(id=session_id, user_id=7))

    try:
        asyncio.run(
            chat.submit_feedback(
                ChatFeedbackRequest(
                    session_id=session_id,
                    request_id="req-feedback",
                    rating="positive",
                ),
                user=SimpleNamespace(id=42),
                db=db,
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("expected session ownership rejection")

    assert db.added == []


def test_submit_feedback_returns_not_found_for_missing_session():
    session_id = uuid.uuid4()
    db = FakeDB(session=None)

    try:
        asyncio.run(
            chat.submit_feedback(
                ChatFeedbackRequest(
                    session_id=session_id,
                    request_id="req-feedback",
                    rating="positive",
                ),
                user=None,
                db=db,
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("expected missing session rejection")

    assert db.added == []
