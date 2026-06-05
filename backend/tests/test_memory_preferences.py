import asyncio
from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException

from app.models.preference import MemoryProposal as MemoryProposalModel
from app.models.preference import UserPreference
from app.routers import chat, preferences
from app.schemas.preferences import UserPreferenceUpdate
from app.services.agent_service.contracts import (
    AgentChatResponse,
    MemoryProposal,
    TraceSummary,
)
from app.services.chatbot.memory import (
    apply_memory_proposal,
    decide_memory_status,
)


class FakeScalarResult:
    def __init__(self, item=None, items=None):
        self.item = item
        self.items = items if items is not None else []

    def scalar_one_or_none(self):
        return self.item

    def scalars(self):
        return SimpleNamespace(all=lambda: self.items)


class FakeDB:
    def __init__(self, existing_preference=None):
        self.added = []
        self.existing_preference = existing_preference
        self.next_memory_proposal_id = 1

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, query):
        return FakeScalarResult(self.existing_preference)

    async def flush(self):
        for obj in self.added:
            if obj.__class__.__name__ == "MemoryProposal" and obj.id is None:
                obj.id = self.next_memory_proposal_id
                self.next_memory_proposal_id += 1


def make_agent_proposal(
    *,
    key="preferred_district",
    confidence=0.9,
    requires_user_confirmation=False,
):
    return MemoryProposal(
        action="upsert",
        key=key,
        value="District 2",
        confidence=confidence,
        evidence="User said they prefer District 2",
        requires_user_confirmation=requires_user_confirmation,
    )


def test_high_confidence_auto_apply_key_auto_applies():
    proposal = make_agent_proposal(
        key="preferred_district",
        confidence=0.9,
        requires_user_confirmation=False,
    )

    assert decide_memory_status(proposal) == "auto_applied"


def test_low_confidence_auto_apply_key_stays_pending():
    proposal = make_agent_proposal(
        key="preferred_district",
        confidence=0.5,
        requires_user_confirmation=False,
    )

    assert decide_memory_status(proposal) == "pending"


def test_confirmation_required_key_stays_pending():
    proposal = make_agent_proposal(
        key="risk_preferences",
        confidence=0.95,
        requires_user_confirmation=True,
    )

    assert decide_memory_status(proposal) == "pending"


def test_handle_memory_proposals_keeps_low_confidence_auto_key_pending():
    db = FakeDB()
    session_id = "00000000-0000-0000-0000-000000000001"
    response = AgentChatResponse(
        request_id="req-memory-low-confidence",
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
                confidence=0.5,
                evidence="User might prefer Da Nang",
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
    preferences = [
        item for item in db.added if item.__class__.__name__ == "UserPreference"
    ]
    assert proposal.status == "pending"
    assert preferences == []
    assert hints[0]["key"] == "preferred_city"


def test_apply_memory_proposal_upserts_preference_and_resolves_proposal():
    existing_preference = UserPreference(
        user_id=42,
        key="preferred_city",
        value_json={"value": "Hue"},
        confidence=0.4,
        source="user",
    )
    db = FakeDB(existing_preference=existing_preference)
    proposal = MemoryProposalModel(
        user_id=42,
        session_id=None,
        request_id="req-apply",
        action="upsert",
        key="preferred_city",
        value_json={"value": "Da Nang"},
        confidence=0.92,
        evidence="User corrected preferred city",
        requires_user_confirmation=True,
        status="pending",
    )

    applied = asyncio.run(apply_memory_proposal(db, proposal=proposal))

    assert applied is existing_preference
    assert existing_preference.value_json == {"value": "Da Nang"}
    assert existing_preference.confidence == 0.92
    assert existing_preference.source == "agent_proposal"
    assert proposal.status == "accepted"
    assert isinstance(proposal.resolved_at, datetime)


def test_patch_preference_uses_body_key_and_forces_user_confidence_source():
    existing_preference = UserPreference(
        user_id=42,
        key="preferred_city",
        value_json={"value": "Hue"},
        confidence=0.25,
        source="agent_proposal",
    )
    db = FakeDB(existing_preference=existing_preference)

    updated = asyncio.run(
        preferences.upsert_preference(
            body=UserPreferenceUpdate(
                key="preferred_city",
                value_json={"value": "Da Nang"},
            ),
            user=SimpleNamespace(id=42),
            db=db,
        )
    )

    assert updated is existing_preference
    assert existing_preference.value_json == {"value": "Da Nang"}
    assert existing_preference.confidence == 1.0
    assert existing_preference.source == "user"


def test_pending_memory_hint_includes_persisted_proposal_id_and_status():
    db = FakeDB()
    session_id = "00000000-0000-0000-0000-000000000001"
    response = AgentChatResponse(
        request_id="req-memory-hint-id",
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
                key="budget_max",
                value=3000000000,
                confidence=0.75,
                evidence="User mentioned an approximate budget",
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

    assert hints == [
        {
            "id": 1,
            "request_id": "req-memory-hint-id",
            "action": "upsert",
            "key": "budget_max",
            "value_json": {"value": 3000000000},
            "confidence": 0.75,
            "evidence": "User mentioned an approximate budget",
            "requires_user_confirmation": True,
            "status": "pending",
        }
    ]


def test_auto_applied_chat_proposal_upserts_existing_preference():
    existing_preference = UserPreference(
        user_id=42,
        key="preferred_city",
        value_json={"value": "Hue"},
        confidence=0.4,
        source="user",
    )
    db = FakeDB(existing_preference=existing_preference)
    response = AgentChatResponse(
        request_id="req-memory-auto-upsert",
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
            SimpleNamespace(id="00000000-0000-0000-0000-000000000001"),
            SimpleNamespace(id=42),
            response,
        )
    )

    added_preferences = [
        item for item in db.added if item.__class__.__name__ == "UserPreference"
    ]
    proposal = [
        item for item in db.added if item.__class__.__name__ == "MemoryProposal"
    ][0]
    assert added_preferences == []
    assert existing_preference.value_json == {"value": "Da Nang"}
    assert existing_preference.confidence == 0.9
    assert existing_preference.source == "agent_proposal"
    assert proposal.status == "auto_applied"
    assert isinstance(proposal.resolved_at, datetime)
    assert hints == []


def test_accept_reject_rejects_already_resolved_proposals():
    proposal = MemoryProposalModel(
        id=7,
        user_id=42,
        session_id=None,
        request_id="req-resolved",
        action="upsert",
        key="preferred_city",
        value_json={"value": "Da Nang"},
        confidence=0.9,
        evidence="Already resolved",
        requires_user_confirmation=True,
        status="accepted",
        resolved_at=datetime(2026, 1, 1),
    )
    db = FakeDB(existing_preference=proposal)

    try:
        asyncio.run(
            preferences.accept_memory_proposal(
                proposal_id=7,
                user=SimpleNamespace(id=42),
                db=db,
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("expected resolved proposal accept to conflict")

    assert proposal.status == "accepted"
    assert proposal.resolved_at == datetime(2026, 1, 1)


def test_reject_rejects_already_resolved_proposals():
    proposal = MemoryProposalModel(
        id=8,
        user_id=42,
        session_id=None,
        request_id="req-resolved-reject",
        action="upsert",
        key="preferred_city",
        value_json={"value": "Da Nang"},
        confidence=0.9,
        evidence="Already resolved",
        requires_user_confirmation=True,
        status="auto_applied",
        resolved_at=datetime(2026, 1, 2),
    )
    db = FakeDB(existing_preference=proposal)

    try:
        asyncio.run(
            preferences.reject_memory_proposal(
                proposal_id=8,
                user=SimpleNamespace(id=42),
                db=db,
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("expected resolved proposal reject to conflict")

    assert proposal.status == "auto_applied"
    assert proposal.resolved_at == datetime(2026, 1, 2)
