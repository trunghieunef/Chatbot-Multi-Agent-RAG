import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph.nodes import _strip_accents
from agent_service.graph.workflow import run_agent_graph


def test_strip_accents_handles_none():
    assert _strip_accents(None) == ""


@pytest.mark.asyncio
async def test_agent_graph_returns_trace_summary_without_llm_key(monkeypatch):
    request = AgentChatRequest(
        request_id="req-graph-1",
        message="Tim can ho Quan 7 duoi 5 ty",
        session_id="session-1",
        user_preferences={"preferred_district": {"value": "Quan 7"}},
    )

    response = await run_agent_graph(request)

    assert response.request_id == "req-graph-1"
    assert response.final_response
    assert "property_search" in response.agents_used
    assert response.trace_summary.intent == "property_search"
    assert response.full_trace["request_id"] == "req-graph-1"
    assert response.full_trace["steps"]
    assert response.readiness["listings"]["status"] == "unknown"
    assert all(
        step["status"] == "success" for step in response.full_trace["steps"]
    )
    assert isinstance(response.full_trace["agent_results"]["property_search"], dict)
    assert response.full_trace["agent_results"]["property_search"]["content"]


@pytest.mark.asyncio
async def test_agent_graph_routes_legal_question_without_llm_key():
    request = AgentChatRequest(
        request_id="req-graph-2",
        message="Tu van phap ly sang ten so do",
        session_id="session-1",
    )

    response = await run_agent_graph(request)

    assert response.agents_used == ["legal_advisor"]
    assert response.trace_summary.intent == "legal_advice"
