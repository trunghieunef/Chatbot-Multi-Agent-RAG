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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get("", response_model=list[UserPreferenceResponse])
async def list_preferences(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserPreference)
        .where(UserPreference.user_id == user.id)
        .order_by(UserPreference.key)
    )
    return result.scalars().all()


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

    if preference is None:
        preference = UserPreference(
            user_id=user.id,
            key=body.key,
            value_json=body.value_json,
            confidence=1.0,
            source="user",
        )
        db.add(preference)
    else:
        preference.value_json = body.value_json
        preference.confidence = 1.0
        preference.source = "user"

    await db.flush()
    return preference


async def _get_user_memory_proposal(
    db: AsyncSession,
    *,
    proposal_id: int,
    user_id: int,
) -> MemoryProposal:
    result = await db.execute(
        select(MemoryProposal).where(
            MemoryProposal.id == proposal_id,
            MemoryProposal.user_id == user_id,
        )
    )
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Memory proposal not found")
    return proposal


def _require_pending_memory_proposal(proposal: MemoryProposal) -> None:
    if proposal.status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Memory proposal already resolved",
        )


@memory_router.post(
    "/{proposal_id}/accept",
    response_model=MemoryProposalResponse,
)
async def accept_memory_proposal(
    proposal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proposal = await _get_user_memory_proposal(
        db,
        proposal_id=proposal_id,
        user_id=user.id,
    )
    _require_pending_memory_proposal(proposal)
    await apply_memory_proposal(db, proposal=proposal)
    return proposal


@memory_router.post(
    "/{proposal_id}/reject",
    response_model=MemoryProposalResponse,
)
async def reject_memory_proposal(
    proposal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proposal = await _get_user_memory_proposal(
        db,
        proposal_id=proposal_id,
        user_id=user.id,
    )
    _require_pending_memory_proposal(proposal)
    proposal.status = "rejected"
    proposal.resolved_at = _utcnow()
    await db.flush()
    return proposal
