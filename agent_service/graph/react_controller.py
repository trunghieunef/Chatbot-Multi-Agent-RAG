from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from agent_service.config import get_agent_settings
from agent_service.graph.query_understanding import ALLOWED_FILTERS
from agent_service.graph.router import ALLOWED_AGENTS


AGENT_RETRIEVAL_DOMAINS = {
    "property_search": ["property"],
    "project_agent": ["project"],
    "news_agent": ["news"],
    "legal_advisor": ["legal"],
    "market_analysis": ["market"],
    "investment_advisor": ["market", "property"],
}

SOURCE_BACKED_AGENTS = {
    "legal_advisor",
    "news_agent",
    "project_agent",
    "property_search",
}
VALID_RETRIEVAL_DOMAINS = {"legal", "market", "news", "project", "property"}


class ReactDecision(BaseModel):
    action: Literal["retrieve_more", "run_specialist", "finalize", "ask_clarification"]
    agents: list[str] = Field(default_factory=list)
    retrieval_domains: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    confidence: float = 0.0
    warnings: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def sanitize_contract_fields(self):
        agents, dropped_agents = _sanitize_list(self.agents, ALLOWED_AGENTS)
        domains, dropped_domains = _sanitize_list(
            self.retrieval_domains,
            VALID_RETRIEVAL_DOMAINS,
        )
        filters = _sanitize_filters(self.filters)
        warnings = list(self.warnings)
        if dropped_agents:
            warnings.append(
                {"code": "react_unknown_agents_dropped", "agents": dropped_agents}
            )
        if dropped_domains:
            warnings.append(
                {"code": "react_unknown_domains_dropped", "domains": dropped_domains}
            )
        self.agents = agents
        self.retrieval_domains = domains
        self.filters = filters
        self.warnings = warnings
        return self


def _sanitize_list(values: list[str], allowed: set[str]) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    dropped: list[str] = []
    for value in values:
        if value in allowed and value not in valid:
            valid.append(value)
        else:
            dropped.append(value)
    return valid, dropped


def _sanitize_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in filters.items() if key in ALLOWED_FILTERS}


def _warning_text(warning: Any) -> str:
    if hasattr(warning, "code"):
        return str(warning.code)
    if isinstance(warning, dict):
        return str(warning.get("code") or warning.get("message") or warning)
    return str(warning)


def _domains_for_agents(agents: list[str]) -> list[str]:
    domains: list[str] = []
    for agent in agents:
        for domain in AGENT_RETRIEVAL_DOMAINS.get(agent, []):
            if domain not in domains:
                domains.append(domain)
    return domains


def _source_backed_agents_to_retry(state: dict[str, Any]) -> list[str]:
    agents = [
        agent
        for agent in state.get("agents_to_run", [])
        if agent in SOURCE_BACKED_AGENTS
    ]
    evidence_for_agent = state.get("evidence_for_agent") or {}
    evidence_by_id = state.get("evidence_by_id") or {}
    agent_results = state.get("agent_results") or {}
    warnings = {_warning_text(warning) for warning in state.get("warnings", [])}
    retry_agents: list[str] = []

    for agent in agents:
        assigned_ids = evidence_for_agent.get(agent) or []
        valid_assigned_ids = [evidence_id for evidence_id in assigned_ids if evidence_id in evidence_by_id]
        result = agent_results.get(agent) or {}
        used_ids = list(result.get("evidence_ids_used") or [])
        used_valid_ids = [evidence_id for evidence_id in used_ids if evidence_id in valid_assigned_ids]
        if (
            not valid_assigned_ids
            or not used_valid_ids
            or "agent_answer_missing_valid_evidence" in warnings
        ):
            retry_agents.append(agent)

    return retry_agents


def _react_filters(state: dict[str, Any]) -> dict[str, Any]:
    understanding = state.get("query_understanding") or {}
    filters = dict(understanding.get("filters") or {})
    filters.update(dict(state.get("routing_filters") or {}))
    return _sanitize_filters(filters)


def _controller_mode_warnings(mode: str) -> list[Any]:
    if mode == "rule":
        return []
    return [
        {
            "code": "react_controller_mode_rule_fallback",
            "configured_mode": mode,
        }
    ]


def decide_react_action(state: dict[str, Any]) -> ReactDecision:
    settings = get_agent_settings()
    iteration = int(state.get("react_iteration") or 0)
    warnings = [_warning_text(warning) for warning in state.get("warnings", [])]
    mode_warnings = _controller_mode_warnings(settings.AGENT_REACT_CONTROLLER_MODE)

    if not settings.AGENT_REACT_ENABLED:
        return ReactDecision(
            action="finalize",
            reason="react disabled",
            confidence=1.0,
            warnings=mode_warnings,
        )

    if iteration >= settings.AGENT_REACT_MAX_ITERATIONS:
        return ReactDecision(
            action="finalize",
            reason="react iteration budget exhausted",
            confidence=1.0,
            warnings=[*mode_warnings, "react_loop_exhausted"],
        )

    retry_agents = _source_backed_agents_to_retry(state)
    if (
        "final_response_missing_sources" in warnings
        or "agent_answer_missing_valid_evidence" in warnings
    ) and retry_agents:
        return ReactDecision(
            action="retrieve_more",
            agents=retry_agents,
            retrieval_domains=_domains_for_agents(retry_agents),
            filters=_react_filters(state),
            reason="source-backed answer is missing validated evidence",
            confidence=1.0,
            warnings=mode_warnings,
        )

    return ReactDecision(
        action="finalize",
        reason="no react action needed",
        confidence=1.0,
        warnings=mode_warnings,
    )
