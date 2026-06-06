from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentSource(BaseModel):
    type: str
    domain: str | None = None
    id: str | int | None = None
    product_id: str | None = None
    title: str | None = None
    url: str | None = None
    snippet: str | None = None
    location: dict[str, Any] | str | None = None
    citation: dict[str, Any] | str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StructuredWarning(BaseModel):
    code: str
    domain: str | None = None
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class MatchedChunk(BaseModel):
    id: str | None = None
    chunk_type: str | None = None
    text: str | None = None
    vector_distance: float | None = None
    semantic_score: float | None = None
    rerank_score: float | None = None
    final_score: float | None = None


class Evidence(BaseModel):
    evidence_id: str
    retrieval_task_id: str
    domain: Literal["property", "project", "news", "legal", "market"]
    source_type: Literal["listing", "project", "article", "market_metric"]
    source_identity: str
    record: dict[str, Any] = Field(default_factory=dict)
    facts: dict[str, Any] = Field(default_factory=dict)
    source: AgentSource
    matched_chunks: list[MatchedChunk] = Field(default_factory=list)
    retrieved_for: list[str] = Field(default_factory=list)
    assigned_to: list[str] = Field(default_factory=list)
    warnings: list[StructuredWarning] = Field(default_factory=list)


class RetrievalTask(BaseModel):
    task_id: str
    domain: Literal["property", "project", "news", "legal", "market"]
    tool: str
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    retrieved_for: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    dependency_mode: Literal["required", "optional_context", "none"] = "none"
    top_k: int = 20
    rerank_top_k: int | None = 5
    timeout_ms: int | None = None


class RetrievalResult(BaseModel):
    task_id: str
    status: Literal["completed", "empty", "failed", "skipped"]
    evidence_ids: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    warnings: list[StructuredWarning] = Field(default_factory=list)
    skip_reason: str | None = None
    error: dict[str, Any] | None = None


class SpecialistResult(BaseModel):
    agent_name: str
    status: Literal["completed", "partial", "no_evidence", "failed", "skipped"]
    content: str
    evidence_ids_used: list[str] = Field(default_factory=list)
    confidence: float | str | None = None
    warnings: list[StructuredWarning] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    sources: list[AgentSource] = Field(default_factory=list)


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
    warnings: list[str | StructuredWarning] = Field(default_factory=list)


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
