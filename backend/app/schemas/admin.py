"""
Pydantic schemas for admin observability endpoints.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AgentTraceListItem(BaseModel):
    """Compact trace row for admin trace lists."""

    id: int
    request_id: str
    session_id: UUID | None = None
    user_id: int | None = None
    intent: str | None = None
    agents_used: list[Any] = Field(default_factory=list)
    trace_summary_json: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float
    status: str
    error_message: str | None = None
    graph_version: str | None = None
    prompt_version: str | None = None
    model_name: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class AgentTraceDetail(AgentTraceListItem):
    """Full trace payload for a single admin trace detail view."""

    full_trace_json: dict[str, Any] = Field(default_factory=dict)
    readiness_json: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True
