from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest, AgentSource, Evidence
from agent_service.graph import nodes
from agent_service.graph.nodes import investment_model_node
from agent_service.graph.workflow import run_agent_graph


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="ev_listing",
        retrieval_task_id="search_property_1",
        domain="property",
        source_type="listing",
        source_identity="listing:p1",
        record={},
        facts={"title": "Can ho Quan 7", "price": 4.8, "area": 75},
        source=AgentSource(type="listing", domain="property", id="p1"),
        retrieved_for=["investment_advisor"],
        assigned_to=["investment_advisor"],
    )


def test_investment_model_node_builds_case_assumptions_metrics_and_trace():
    state = {
        "request": AgentChatRequest(
            request_id="req-invest-node",
            session_id="s1",
            message="Co nen dau tu can ho nay khong?",
            user_preferences={"interest_rate_annual": {"value": 0.095}},
        ),
        "agents_to_run": ["investment_advisor"],
        "evidence_by_id": {"ev_listing": _evidence()},
        "evidence_for_agent": {"investment_advisor": ["ev_listing"]},
        "query_understanding": {
            "filters": {
                "expected_monthly_rent": 18_000_000,
                "loan_ratio": 0.6,
            }
        },
        "trace_steps": [],
        "warnings": [],
    }

    result = investment_model_node(state)

    assert result["investment_case"]["property_summary"]["evidence_ids"] == ["ev_listing"]
    assert result["investment_assumptions"]["loan_ratio"]["value"] == 0.6
    assert "price_per_m2" in result["investment_metrics"]
    assert result["trace_steps"][-1]["step_name"] == "investment_model"


@pytest.mark.asyncio
async def test_investment_graph_runs_investment_model_step(monkeypatch):
    async def fake_readiness_snapshot():
        return {
            "listings": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "projects": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "news": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "legal": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
        }

    monkeypatch.setattr(nodes, "build_readiness_snapshot", fake_readiness_snapshot)

    response = await run_agent_graph(
        AgentChatRequest(
            request_id="req-invest-graph-route",
            session_id="s1",
            message="Co nen dau tu can ho Quan 7 nay khong?",
        )
    )

    step_names = [step["step_name"] for step in response.full_trace["steps"]]
    assert "investment_model" in step_names
    assert step_names.index("investment_model") > step_names.index("specialist_agents")
    assert step_names.index("investment_model") < step_names.index("synthesizer")
