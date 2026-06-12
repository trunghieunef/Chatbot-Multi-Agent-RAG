from __future__ import annotations

import unicodedata
from typing import Any

from pydantic import BaseModel, Field

from agent_service.config import get_agent_settings
from agent_service.llm.gemini import GeminiClient


ALLOWED_AGENTS = {
    "property_search",
    "project_agent",
    "market_analysis",
    "news_agent",
    "legal_advisor",
    "investment_advisor",
}

AGENT_ORDER = [
    "legal_advisor",
    "investment_advisor",
    "market_analysis",
    "news_agent",
    "project_agent",
    "property_search",
]

INTENT_BY_AGENT = {
    "legal_advisor": "legal_advice",
    "investment_advisor": "investment_advice",
    "market_analysis": "market_analysis",
    "news_agent": "news",
    "project_agent": "project",
    "property_search": "property_search",
}

KEYWORDS_BY_AGENT = {
    "legal_advisor": ["phap ly", "luat", "thu tuc", "cong chung", "so do", "sang ten"],
    "investment_advisor": ["dau tu", "roi", "loi nhuan", "sinh loi", "rental yield"],
    "market_analysis": ["thi truong", "xu huong", "thong ke", "gia trung binh"],
    "news_agent": ["tin tuc", "bao chi", "cap nhat"],
    "project_agent": ["du an", "chu dau tu"],
    "property_search": ["tim", "mua", "thue", "can ho", "nha", "dat", "quan "],
}


class RouterDecision(BaseModel):
    intent: str
    agents: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    filters: dict[str, Any] = Field(default_factory=dict)
    needs_clarification: bool = False
    clarifying_question: str | None = None
    reason: str = ""
    mode: str = "rule"
    warnings: list[Any] = Field(default_factory=list)


def _strip_accents(value: str | None) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    without_marks = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return without_marks.lower()


def _normalized_tokens(value: str) -> set[str]:
    import re

    return set(re.findall(r"[a-z0-9]+", value))


def _keyword_matches(
    keyword: str,
    normalized_query: str,
    normalized_tokens: set[str],
) -> bool:
    normalized_keyword = _strip_accents(keyword)
    stripped_keyword = normalized_keyword.strip()
    if not stripped_keyword:
        return False
    if stripped_keyword != normalized_keyword or " " in stripped_keyword:
        return normalized_keyword in normalized_query
    return stripped_keyword in normalized_tokens


def sanitize_agents(agents: list[str]) -> tuple[list[str], list[str]]:
    valid = []
    dropped = []
    for agent in agents:
        if agent in ALLOWED_AGENTS and agent not in valid:
            valid.append(agent)
        else:
            dropped.append(agent)
    return valid, dropped


def route_with_rules(state: dict[str, Any]) -> RouterDecision:
    request = state["request"]
    normalized_query = state.get("normalized_query") or _strip_accents(request.message)
    normalized_tokens = _normalized_tokens(normalized_query)
    agents = [
        agent
        for agent in AGENT_ORDER
        if any(
            _keyword_matches(keyword, normalized_query, normalized_tokens)
            for keyword in KEYWORDS_BY_AGENT[agent]
        )
    ]

    if not agents:
        agents = ["property_search"]

    intent = INTENT_BY_AGENT[agents[0]] if len(agents) == 1 else "mixed"
    return RouterDecision(
        intent=intent,
        agents=agents,
        confidence=1.0,
        filters={
            "locale": request.locale,
            "user_preferences": request.user_preferences,
        },
        reason="keyword rules",
        mode="rule",
    )


def merge_router_decisions(
    rule: RouterDecision,
    llm: RouterDecision,
    *,
    confidence_threshold: float,
) -> RouterDecision:
    agents = list(rule.agents)
    if llm.confidence >= confidence_threshold:
        for agent in llm.agents:
            if agent not in agents:
                agents.append(agent)
    if not agents:
        agents = ["property_search"]
    return RouterDecision(
        intent=rule.intent if len(agents) == 1 else "mixed",
        agents=agents,
        confidence=max(rule.confidence, llm.confidence),
        filters={**llm.filters, **rule.filters},
        mode="hybrid",
        reason=f"rule={rule.reason}; llm={llm.reason}",
        warnings=[*rule.warnings, *llm.warnings],
    )


def _router_prompt(query: str) -> str:
    return (
        "Ban la bo dinh tuyen intent bat dong san. Tra ve JSON duy nhat voi "
        "intent, agents, confidence, filters, needs_clarification, "
        "clarifying_question, reason. Khong tra loi nguoi dung.\n"
        f"Query: {query}"
    )


async def route_with_llm(
    state: dict[str, Any],
    client: GeminiClient | None = None,
) -> RouterDecision:
    request = state["request"]
    settings = get_agent_settings()
    client = client or GeminiClient()
    try:
        payload = await client.generate_json(_router_prompt(request.message))
        decision = RouterDecision.model_validate(payload)
    except Exception:
        return RouterDecision(
            intent="fallback",
            agents=[],
            confidence=0.0,
            mode="fallback",
            reason="invalid llm router output",
            warnings=["llm_router_invalid_json"],
        )

    agents, dropped = sanitize_agents(decision.agents)
    warnings = list(decision.warnings)
    if dropped:
        warnings.append({"code": "llm_router_unknown_agents", "agents": dropped})
    if decision.confidence < settings.AGENT_LLM_CONFIDENCE_THRESHOLD:
        warnings.append("llm_router_low_confidence")
    return decision.model_copy(
        update={
            "agents": agents,
            "warnings": warnings,
            "mode": "llm",
        }
    )


async def route_request(
    state: dict[str, Any],
    client: GeminiClient | None = None,
) -> RouterDecision:
    settings = get_agent_settings()
    rule = route_with_rules(state)
    if state.get("force_deterministic") or settings.AGENT_ROUTER_MODE == "rule":
        return rule

    llm = await route_with_llm(state, client=client)
    if settings.AGENT_ROUTER_MODE == "llm":
        if llm.confidence >= settings.AGENT_LLM_CONFIDENCE_THRESHOLD and llm.agents:
            return llm
        return rule.model_copy(
            update={
                "mode": "fallback",
                "warnings": [*rule.warnings, *llm.warnings],
                "reason": f"{rule.reason}; llm fallback={llm.reason}",
            }
        )

    return merge_router_decisions(
        rule,
        llm,
        confidence_threshold=settings.AGENT_LLM_CONFIDENCE_THRESHOLD,
    )
