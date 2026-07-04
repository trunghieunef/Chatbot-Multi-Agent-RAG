from __future__ import annotations

import pytest

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentChatRequest
from agent_service.graph.agentic_workflow import _node_synthesize
from agent_service.graph.router import route_request, route_with_rules


def _state(message: str, normalized: str | None = None) -> dict:
    return {
        "normalized_query": normalized or message.lower(),
        "request": AgentChatRequest(
            request_id="req-offtopic",
            session_id="session-1",
            message=message,
        ),
    }


class _LLMStub:
    def __init__(self, payload: dict):
        self.payload = payload

    async def generate_json(self, prompt, timeout_seconds=None):
        return self.payload


def test_keyword_query_routes_to_agents_not_smalltalk():
    decision = route_with_rules(
        _state("Chào giá căn hộ quận 7", normalized="chao gia can ho quan 7")
    )
    assert decision.agents


@pytest.mark.asyncio
async def test_route_request_respects_llm_greeting(monkeypatch):
    settings = get_agent_settings()
    monkeypatch.setattr(settings, "AGENT_ROUTER_MODE", "llm")
    stub = _LLMStub(
        {"intent": "greeting", "agents": [], "confidence": 0.95, "reason": "small talk"}
    )
    decision = await route_request(_state("hi"), client=stub)
    assert decision.intent == "greeting"
    assert decision.agents == []


@pytest.mark.asyncio
async def test_route_request_respects_llm_off_topic(monkeypatch):
    settings = get_agent_settings()
    monkeypatch.setattr(settings, "AGENT_ROUTER_MODE", "llm")
    stub = _LLMStub(
        {
            "intent": "off_topic",
            "agents": [],
            "confidence": 0.95,
            "reason": "not real estate",
        }
    )
    decision = await route_request(
        _state("hôm nay thời tiết thế nào", normalized="hom nay thoi tiet the nao"),
        client=stub,
    )
    assert decision.intent == "off_topic"
    assert decision.agents == []


@pytest.mark.asyncio
async def test_route_request_low_confidence_off_topic_falls_back(monkeypatch):
    # An unsure off_topic verdict must not hijack routing away from agents.
    settings = get_agent_settings()
    monkeypatch.setattr(settings, "AGENT_ROUTER_MODE", "llm")
    stub = _LLMStub(
        {"intent": "off_topic", "agents": [], "confidence": 0.2, "reason": "unsure"}
    )
    decision = await route_request(
        _state("tìm nhà quận 2", normalized="tim nha quan 2"), client=stub
    )
    assert decision.agents  # rule fallback keeps serving the query


@pytest.mark.asyncio
async def test_synthesize_off_topic_steers_back_to_real_estate():
    state = {
        "request": AgentChatRequest(
            request_id="req-synth-offtopic",
            session_id="session-1",
            message="hôm nay thời tiết thế nào",
        ),
        "supervisor_plan": {"intent": "off_topic", "selected_agents": []},
        "_agent_results": {},
    }
    out = await _node_synthesize(state)
    assert "bất động sản" in out["final_response"]
    assert out["suggested_actions"]


@pytest.mark.asyncio
async def test_synthesize_greeting_says_hello():
    state = {
        "request": AgentChatRequest(
            request_id="req-synth-greeting",
            session_id="session-1",
            message="hi",
        ),
        "supervisor_plan": {"intent": "greeting", "selected_agents": []},
        "_agent_results": {},
    }
    out = await _node_synthesize(state)
    assert "Xin chào" in out["final_response"]
