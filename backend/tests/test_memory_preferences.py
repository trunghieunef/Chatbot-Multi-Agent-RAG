import asyncio
from datetime import datetime
from types import SimpleNamespace

from app.models.preference import MemoryProposal as MemoryProposalModel
from app.models.preference import UserPreference
from app.routers import chat
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

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, query):
        return FakeScalarResult(self.existing_preference)

    async def flush(self):
        return None


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
        confidence=0.79,
        requires_user_confirmation=False,
    )

    assert decide_memory_status(proposal) == "pending"


def test_confirmation_required_key_stays_pending():
    proposal = make_agent_proposal(
        key="budget_max",
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

    hints = chat.handle_memory_proposals(
        db,
        SimpleNamespace(id=session_id),
        SimpleNamespace(id=42),
        response,
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
