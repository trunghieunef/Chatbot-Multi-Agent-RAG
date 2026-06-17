import pytest

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentChatRequest
from agent_service.graph.router import (
    RouterDecision,
    merge_router_decisions,
    route_with_llm,
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


@pytest.mark.asyncio
async def test_llm_router_uses_router_timeout(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_ROUTER_TIMEOUT_SECONDS", "1.25")
    get_agent_settings.cache_clear()
    seen = {}

    class FakeClient:
        async def generate_json(self, prompt, *, timeout_seconds=None):
            seen["timeout_seconds"] = timeout_seconds
            return {
                "intent": "property_search",
                "agents": ["property_search"],
                "confidence": 0.9,
                "filters": {},
                "needs_clarification": False,
                "clarifying_question": None,
                "reason": "fake",
            }

    state = {
        "normalized_query": "tim can ho",
        "request": AgentChatRequest(
            request_id="req-router-timeout",
            message="tim can ho",
            session_id="session-1",
        ),
    }

    await route_with_llm(state, client=FakeClient())

    assert seen["timeout_seconds"] == 1.25
    get_agent_settings.cache_clear()
