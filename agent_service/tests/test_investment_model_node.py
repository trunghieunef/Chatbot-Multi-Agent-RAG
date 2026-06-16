from __future__ import annotations

from agent_service.contracts import AgentChatRequest, AgentSource, Evidence
from agent_service.graph.nodes import investment_model_node


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
