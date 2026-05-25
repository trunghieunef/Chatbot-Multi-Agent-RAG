"""Shared contracts for the production chatbot pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RoutingDecision:
    """Intent classification and agent routing output."""

    intent: str
    target_agents: list[str]
    search_filters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResult:
    """Normalized output from one chatbot agent."""

    agent_name: str
    content: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    confidence: float = 0.0
