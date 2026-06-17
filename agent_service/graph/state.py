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
    force_deterministic: bool
    intent: str
    agents_to_run: list[str]
    routing_filters: dict[str, Any]
    needs_clarification: bool
    clarifying_question: str | None
    compact_context: list[dict[str, str]]
    query_understanding: dict[str, Any]
    readiness: dict[str, Any]
    retrieval_plan: list[RetrievalTask]
    retrieval_results: dict[str, RetrievalResult]
    evidence_by_id: dict[str, Evidence]
    evidence_for_agent: dict[str, list[str]]
    evidence: dict[str, list[dict[str, Any]]]
    agent_results: dict[str, dict[str, Any]]
    agent_blackboard: dict[str, Any]
    investment_case: dict[str, Any]
    investment_assumptions: dict[str, Any]
    investment_metrics: dict[str, Any]
    committee_review: dict[str, Any]
    final_response: str
    sources: list[AgentSource]
    suggested_actions: list[str]
    memory_proposals: list[MemoryProposal]
    react_iteration: int
    react_decision: dict[str, Any]
    react_actions: list[dict[str, Any]]
    loop_warnings: list[str | StructuredWarning]
    trace_steps: list[dict[str, Any]]
    warnings: list[str | StructuredWarning]

