from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preference import MemoryProposal as MemoryProposalRecord
from app.models.preference import UserPreference
from app.services.agent_service.contracts import MemoryProposal as AgentMemoryProposal


AUTO_APPLY_KEYS = {
    "preferred_city",
    "preferred_district",
    "preferred_property_type",
    "budget_max",
    "budget_min",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def decide_memory_status(proposal: AgentMemoryProposal | MemoryProposalRecord) -> str:
    if proposal.requires_user_confirmation:
        return "pending"
    if proposal.key in AUTO_APPLY_KEYS and proposal.confidence >= 0.8:
        return "auto_applied"
    return "pending"


async def apply_memory_proposal(
    db: AsyncSession,
    *,
    proposal: MemoryProposalRecord,
) -> UserPreference:
    if proposal.user_id is None:
        raise ValueError("Cannot apply memory proposal without a user_id")

    preference = await upsert_user_preference(
        db,
        user_id=proposal.user_id,
        key=proposal.key,
        value_json=proposal.value_json,
        confidence=proposal.confidence,
        source="agent_proposal",
    )
    proposal.status = "accepted"
    proposal.resolved_at = _utcnow()
    await db.flush()
    return preference


async def upsert_user_preference(
    db: AsyncSession,
    *,
    user_id: int,
    key: str,
    value_json: dict,
    confidence: float,
    source: str = "agent_proposal",
) -> UserPreference:
    result = await db.execute(
        select(UserPreference).where(
            UserPreference.user_id == user_id,
            UserPreference.key == key,
        )
    )
    preference = result.scalar_one_or_none()

    if preference is None:
        preference = UserPreference(
            user_id=user_id,
            key=key,
            value_json=value_json,
            confidence=confidence,
            source=source,
        )
        db.add(preference)
    else:
        preference.value_json = value_json
        preference.confidence = confidence
        preference.source = source

    await db.flush()
    return preference


def mark_memory_proposal_resolved(
    proposal: MemoryProposalRecord,
    *,
    status: str,
) -> None:
    proposal.status = status
    proposal.resolved_at = _utcnow()
