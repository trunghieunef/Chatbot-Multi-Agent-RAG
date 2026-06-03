from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentSource(BaseModel):
    type: str
    id: int | None = None
    product_id: str | None = None
    title: str | None = None
    url: str | None = None
    location: str | None = None
    citation: dict[str, Any] | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationContextItem(BaseModel):
    role: str
    content: str
    created_at: str | None = None
    sources: list[AgentSource] = Field(default_factory=list)


class AgentChatRequest(BaseModel):
    request_id: str
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str
    user_id: int | None = None
    is_authenticated: bool = False
    conversation_context: list[ConversationContextItem] = Field(default_factory=list)
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    requested_trace_level: str = "full"
    locale: str = "vi-VN"


class TraceSummary(BaseModel):
    intent: str = "unknown"
    agents: list[str] = Field(default_factory=list)
    source_count: int = 0
    latency_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class MemoryProposal(BaseModel):
    action: str
    key: str
    value: Any
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: str
    requires_user_confirmation: bool = True


class AgentChatResponse(BaseModel):
    request_id: str
    final_response: str
    agents_used: list[str] = Field(default_factory=list)
    sources: list[AgentSource] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    trace_summary: TraceSummary = Field(default_factory=TraceSummary)
    full_trace: dict[str, Any] = Field(default_factory=dict)
    memory_proposals: list[MemoryProposal] = Field(default_factory=list)
    readiness: dict[str, Any] = Field(default_factory=dict)
    evaluation_candidate: dict[str, Any] = Field(default_factory=dict)
