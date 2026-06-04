from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserPreferenceUpdate(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    value_json: dict[str, Any]


class UserPreferenceResponse(BaseModel):
    id: int
    user_id: int
    key: str
    value_json: dict[str, Any]
    confidence: float
    source: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MemoryProposalUpdate(BaseModel):
    status: Literal["accepted", "rejected"]


class MemoryProposalResponse(BaseModel):
    id: int
    user_id: int | None = None
    session_id: UUID | None = None
    request_id: str
    action: str
    key: str
    value_json: dict[str, Any]
    confidence: float
    evidence: str
    requires_user_confirmation: bool
    status: str
    created_at: datetime | None = None
    resolved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
