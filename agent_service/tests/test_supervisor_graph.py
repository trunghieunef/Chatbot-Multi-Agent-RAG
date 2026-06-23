from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest, AgentResult
from agent_service.graph.router import RouterDecision
from agent_service.graph import agentic_workflow as wf


@pytest.mark.asyncio
async def test_only_selected_agents_run_and_response_is_built(monkeypatch):
    # Supervisor selects exactly property_search + market_analysis.
    async def fake_route_request(state, client=None):
        return RouterDecision(intent="mixed",
                              agents=["property_search", "market_analysis"],
                              confidence=0.9, filters={"city": "HCM"})

    ran = []

    async def fake_run_specialist(*, agent_name, context, registry, llm_client, settings):
        ran.append(agent_name)
        return AgentResult(agent_name=agent_name, status="completed",
                           content=f"{agent_name} ok", evidence_ids_used=[f"ev_{agent_name}"])

    monkeypatch.setattr(wf, "route_request", fake_route_request)
    monkeypatch.setattr(wf, "run_specialist", fake_run_specialist)
    # Force deterministic synth (no LLM) for a stable assertion.
    monkeypatch.setattr(wf, "_make_llm_client", lambda settings: None)

    resp = await wf.run_agentic_graph(AgentChatRequest(
        request_id="r1", session_id="s1", message="So sánh giá căn hộ Quận 7"))

    assert sorted(ran) == ["market_analysis", "property_search"]
    assert "legal_advisor" not in ran        # NOT a fan-out of all 6
    assert resp.agents_used == ["property_search", "market_analysis"]
    assert "property_search ok" in resp.final_response
    assert "market_analysis ok" in resp.final_response


@pytest.mark.asyncio
async def test_clarification_short_circuits_specialists(monkeypatch):
    async def fake_route_request(state, client=None):
        return RouterDecision(intent="property_search", agents=["property_search"],
                              needs_clarification=True,
                              clarifying_question="Bạn muốn mua hay thuê?")

    async def fail_specialist(**kwargs):
        raise AssertionError("specialists must not run on clarification")

    monkeypatch.setattr(wf, "route_request", fake_route_request)
    monkeypatch.setattr(wf, "run_specialist", fail_specialist)
    monkeypatch.setattr(wf, "_make_llm_client", lambda settings: None)

    resp = await wf.run_agentic_graph(AgentChatRequest(
        request_id="r2", session_id="s1", message="Tìm căn hộ Quận 7"))
    assert resp.final_response == "Bạn muốn mua hay thuê?"
    assert resp.agents_used == []
