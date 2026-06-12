from agent_service.contracts import AgentChatRequest
from agent_service.graph.router import (
    RouterDecision,
    merge_router_decisions,
    route_with_rules,
)


def test_hybrid_router_keeps_rule_legal_keyword_and_llm_investment():
    state = {
        "normalized_query": "phap ly va dau tu can ho quan 7",
        "request": AgentChatRequest(
            request_id="req-router",
            message="phap ly va dau tu can ho quan 7",
            session_id="session-1",
        ),
    }
    llm_decision = RouterDecision(
        intent="investment_advice",
        agents=["investment_advisor"],
        confidence=0.9,
        filters={},
        needs_clarification=False,
        clarifying_question=None,
        reason="investment language",
        mode="llm",
        warnings=[],
    )

    merged = merge_router_decisions(
        route_with_rules(state),
        llm_decision,
        confidence_threshold=0.65,
    )

    assert "legal_advisor" in merged.agents
    assert "investment_advisor" in merged.agents
