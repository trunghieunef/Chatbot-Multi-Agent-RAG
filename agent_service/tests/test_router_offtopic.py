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
    """generate_json stub; fails the test if called when it must not be."""

    def __init__(self, payload: dict | None = None, forbid_call: bool = False):
        self.payload = payload or {}
        self.forbid_call = forbid_call

    async def generate_json(self, prompt, timeout_seconds=None):
        if self.forbid_call:
            raise AssertionError("LLM must not be called for a rule-level greeting")
        return self.payload


def test_rule_router_detects_greeting():
    decision = route_with_rules(_state("hi"))
    assert decision.intent == "greeting"
    assert decision.agents == []


def test_rule_router_detects_vietnamese_greeting():
    decision = route_with_rules(_state("Xin chào", normalized="xin chao"))
    assert decision.intent == "greeting"
    assert decision.agents == []


def test_keywords_beat_greeting_prefix():
    # "chào giá căn hộ quận 7" opens with a greeting word but carries real
    # keywords — it must route to agents, not small talk.
    decision = route_with_rules(
        _state("Chào giá căn hộ quận 7", normalized="chao gia can ho quan 7")
    )
    assert decision.intent != "greeting"
    assert decision.agents


def test_keywordless_non_greeting_still_falls_back_to_property_search():
    decision = route_with_rules(_state("abc xyz", normalized="abc xyz"))
    assert decision.agents == ["property_search"]


@pytest.mark.asyncio
async def test_route_request_greeting_skips_llm():
    decision = await route_request(_state("hi"), client=_LLMStub(forbid_call=True))
    assert decision.intent == "greeting"
    assert decision.agents == []


@pytest.mark.asyncio
async def test_route_request_respects_llm_off_topic(monkeypatch):
    settings = get_agent_settings()
    monkeypatch.setattr(settings, "AGENT_ROUTER_MODE", "llm")
    stub = _LLMStub(
        payload={
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
