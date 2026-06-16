from __future__ import annotations

from agent_service.contracts import AgentChatRequest
from agent_service.graph.router import RouterDecision, merge_router_decisions, route_with_rules


def test_rule_router_routes_mixed_legal_investment_property():
    state = {
        "normalized_query": "tim can ho quan 7 phap ly va dau tu",
        "request": AgentChatRequest(
            request_id="req-router-rules",
            session_id="session-1",
            message="Tim can ho Quan 7 phap ly va dau tu",
        ),
    }

    decision = route_with_rules(state)

    assert set(decision.agents) >= {
        "property_search",
        "legal_advisor",
        "investment_advisor",
    }


def test_hybrid_router_merges_valid_llm_agent():
    rule = RouterDecision(
        intent="property_search",
        agents=["property_search"],
        confidence=1.0,
        reason="rule",
    )
    llm = RouterDecision(
        intent="legal_advice",
        agents=["legal_advisor"],
        confidence=0.9,
        reason="llm",
    )

    merged = merge_router_decisions(rule, llm, confidence_threshold=0.65)

    assert merged.mode == "hybrid"
    assert merged.agents == ["property_search", "legal_advisor"]
