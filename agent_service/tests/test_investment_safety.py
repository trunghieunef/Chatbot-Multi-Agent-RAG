from __future__ import annotations

from agent_service.graph.nodes import safety_validator_node


def test_safety_warns_when_investment_answer_lacks_disclaimer():
    result = safety_validator_node(
        {
            "final_response": "Nen dau tu ngay.",
            "sources": [],
            "suggested_actions": [],
            "agents_to_run": ["investment_advisor"],
            "warnings": [],
            "agent_results": {},
            "evidence_by_id": {},
            "evidence_for_agent": {},
            "trace_steps": [],
        }
    )

    assert "financial_disclaimer_missing" in result["warnings"]


def test_safety_downgrades_high_confidence_committee_with_missing_inputs():
    result = safety_validator_node(
        {
            "final_response": "Scorecard dau tu\nLuu y: khong phai loi khuyen tai chinh.",
            "sources": [],
            "suggested_actions": [],
            "agents_to_run": ["investment_advisor"],
            "warnings": [],
            "agent_results": {},
            "evidence_by_id": {},
            "evidence_for_agent": {},
            "committee_review": {
                "recommendation": {
                    "decision": "consider",
                    "confidence": "high",
                    "required_confirmations": ["expected_monthly_rent"],
                }
            },
            "trace_steps": [],
        }
    )

    assert "committee_high_confidence_with_missing_inputs" in result["warnings"]
    assert result["committee_review"]["recommendation"]["confidence"] == "medium"
