from __future__ import annotations

from typing import Any, TypedDict

from agent_service.contracts import AgentChatRequest, AgentSource, MemoryProposal


class AgentGraphState(TypedDict, total=False):
    request: AgentChatRequest
    normalized_query: str
    intent: str
    agents_to_run: list[str]
    routing_filters: dict[str, Any]
    readiness: dict[str, Any]
    evidence: dict[str, list[AgentSource]]
    agent_results: dict[str, str]
    final_response: str
    sources: list[AgentSource]
    suggested_actions: list[str]
    memory_proposals: list[MemoryProposal]
    trace_steps: list[dict[str, Any]]
    warnings: list[str]
