from __future__ import annotations

from agent_service.contracts import AgentChatRequest
from agent_service.graph.workflow import _response_from_result


def test_response_full_trace_includes_investment_artifacts():
    request = AgentChatRequest(
        request_id="req-trace-invest",
        session_id="s1",
        message="Co nen dau tu can ho nay?",
    )

    response = _response_from_result(
        request,
        {
            "intent": "investment_advice",
            "agents_to_run": ["investment_advisor"],
            "final_response": "Scorecard dau tu",
            "sources": [],
            "suggested_actions": [],
            "trace_steps": [],
            "warnings": [],
            "agent_blackboard": {"entries": [{"id": "bb1"}]},
            "investment_case": {"case_scope": "single_listing"},
            "investment_assumptions": {"loan_ratio": {"value": 0.6}},
            "investment_metrics": {"price_per_m2": {"value": 64.0}},
            "committee_review": {
                "recommendation": {"decision": "need_more_info"}
            },
        },
    )

    trace = response.full_trace
    assert trace["agent_blackboard"]["entries"][0]["id"] == "bb1"
    assert trace["investment_case"]["case_scope"] == "single_listing"
    assert trace["investment_assumptions"]["loan_ratio"]["value"] == 0.6
    assert trace["investment_metrics"]["price_per_m2"]["value"] == 64.0
    assert trace["committee_review"]["recommendation"]["decision"] == "need_more_info"
