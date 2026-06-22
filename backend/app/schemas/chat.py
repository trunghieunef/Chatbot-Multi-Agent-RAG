"""
Pydantic schemas for Chat endpoints.
"""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    """User sends a chat message."""
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: UUID | None = None  # None = create new session


class ChatFeedbackRequest(BaseModel):
    """Feedback for a specific chat response."""
    session_id: UUID
    request_id: str = Field(..., min_length=1, max_length=80)
    rating: str = Field(..., min_length=1, max_length=20)
    issue_type: str | None = Field(default=None, max_length=80)
    comment: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ChatFeedbackResponse(BaseModel):
    """Identifier for a stored chat feedback record."""
    id: int


class ChatMessageResponse(BaseModel):
    """Response from the chatbot."""
    session_id: UUID
    role: str
    content: str
    agent_used: str | None = None
    agents_used: list[str] = Field(default_factory=list)
    sources: list[dict] | None = None
    suggested_actions: list[str] | None = None
    trace_summary: dict | None = None
    memory_hints: list[dict] | None = None
    charts: list[dict] | None = None
    feedback_id: str | None = None
    request_id: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ChatSessionResponse(BaseModel):
    """Chat session summary."""
    id: UUID
    title: str | None = None
    message_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ChatHistoryResponse(BaseModel):
    """Full chat history for a session."""
    session: ChatSessionResponse
    messages: list[ChatMessageResponse]


class ChatSessionUpdate(BaseModel):
    """Request to update a chat session (rename)."""
    title: str = Field(..., min_length=1, max_length=300)
