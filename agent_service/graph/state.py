from __future__ import annotations

from typing import Any, TypedDict

from agent_service.contracts import (
    AgentChatRequest,
    AgentSource,
    Evidence,
    MemoryProposal,
    RetrievalResult,
    RetrievalTask,
    StructuredWarning,
)


class AgentGraphState(TypedDict, total=False):
    request: AgentChatRequest
    normalized_query: str
    intent: str
    agents_to_run: list[str]
    routing_filters: dict[str, Any]
    readiness: dict[str, Any]
    retrieval_plan: list[RetrievalTask]
    retrieval_results: dict[str, RetrievalResult]
    evidence_by_id: dict[str, Evidence]
    evidence_for_agent: dict[str, list[str]]
    evidence: dict[str, list[dict[str, Any]]]
    agent_results: dict[str, dict[str, Any]]
    final_response: str
    sources: list[AgentSource]
    suggested_actions: list[str]
    memory_proposals: list[MemoryProposal]
    trace_steps: list[dict[str, Any]]
    warnings: list[str | StructuredWarning]
