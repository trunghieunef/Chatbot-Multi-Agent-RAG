from __future__ import annotations

from agent_service.graph.committee import build_committee_review


def test_committee_review_returns_structured_perspectives_and_need_more_info():
    review = build_committee_review(
        investment_case={
            "missing_evidence": ["market", "legal"],
            "property_summary": {"evidence_ids": ["ev_listing"]},
            "market_summary": {"evidence_ids": []},
            "legal_summary": {"evidence_ids": []},
        },
        investment_assumptions={
            "expected_monthly_rent": {
                "value": None,
                "source": "default",
                "depends_on": [],
                "evidence_ids": [],
                "unit": "vnd_per_month",
                "note": "",
            }
        },
        investment_metrics={
            "price_per_m2": {
                "value": 64.0,
                "unit": "million_vnd_per_m2",
                "depends_on": ["purchase_price", "area"],
                "formula": "",
                "confidence": "high",
                "warnings": [],
            },
            "metric_warnings": {
                "value": 1,
                "unit": "count",
                "depends_on": [],
                "formula": "",
                "confidence": "high",
                "warnings": ["missing_expected_monthly_rent"],
            },
        },
        agent_blackboard={"entries": []},
        warnings=[],
    )

    roles = {item["role"] for item in review["perspectives"]}
    assert {
        "bull",
        "bear",
        "legal_risk",
        "market_risk",
        "finance",
        "missing_inputs",
    }.issubset(roles)
    assert review["recommendation"]["decision"] == "need_more_info"
    assert review["recommendation"]["confidence"] == "low"
    assert (
        "expected_monthly_rent"
        in review["recommendation"]["required_confirmations"]
    )


def test_committee_review_consider_is_not_high_confidence_when_defaults_drive_metrics():
    review = build_committee_review(
        investment_case={
            "missing_evidence": [],
            "property_summary": {"evidence_ids": ["ev_listing"]},
            "market_summary": {"evidence_ids": ["ev_market"]},
            "legal_summary": {"evidence_ids": ["ev_legal"]},
        },
        investment_assumptions={
            "loan_ratio": {
                "value": 0.6,
                "source": "default",
                "depends_on": [],
                "evidence_ids": [],
                "unit": "ratio_0_1",
                "note": "",
            },
            "expected_monthly_rent": {
                "value": 18_000_000,
                "source": "user",
                "depends_on": [],
                "evidence_ids": [],
                "unit": "vnd_per_month",
                "note": "",
            },
        },
        investment_metrics={
            "net_yield": {
                "value": 0.0414,
                "unit": "ratio_0_1",
                "depends_on": ["gross_yield", "operating_cost_ratio"],
                "formula": "",
                "confidence": "medium",
                "warnings": [],
            },
            "monthly_cashflow_estimate": {
                "value": 0.0101,
                "unit": "billion_vnd_per_month",
                "depends_on": [],
                "formula": "",
                "confidence": "medium",
                "warnings": [],
            },
            "metric_warnings": {
                "value": 0,
                "unit": "count",
                "depends_on": [],
                "formula": "",
                "confidence": "high",
                "warnings": [],
            },
        },
        agent_blackboard={"entries": []},
        warnings=[],
    )

    assert review["recommendation"]["decision"] == "consider"
    assert review["recommendation"]["confidence"] == "medium"


def test_committee_review_uses_legal_specialist_blackboard_evidence():
    review = build_committee_review(
        investment_case={
            "missing_evidence": ["legal"],
            "property_summary": {"evidence_ids": ["ev_listing"]},
            "market_summary": {"evidence_ids": ["ev_market"]},
            "legal_summary": {"evidence_ids": []},
        },
        investment_assumptions={
            "expected_monthly_rent": {
                "value": 18_000_000,
                "source": "user",
                "depends_on": [],
                "evidence_ids": [],
                "unit": "vnd_per_month",
                "note": "",
            }
        },
        investment_metrics={
            "net_yield": {
                "value": 0.0414,
                "unit": "ratio_0_1",
                "depends_on": ["gross_yield"],
                "formula": "",
                "confidence": "medium",
                "warnings": [],
            },
            "monthly_cashflow_estimate": {
                "value": 0.0101,
                "unit": "billion_vnd_per_month",
                "depends_on": [],
                "formula": "",
                "confidence": "medium",
                "warnings": [],
            },
            "metric_warnings": {
                "value": 0,
                "unit": "count",
                "depends_on": [],
                "formula": "",
                "confidence": "high",
                "warnings": [],
            },
        },
        agent_blackboard={
            "entries": [
                {
                    "author": "legal_advisor",
                    "type": "specialist_result",
                    "evidence_ids": ["ev_legal"],
                    "confidence": "medium",
                    "content": {"status": "completed"},
                }
            ]
        },
        warnings=[],
    )

    legal = next(item for item in review["perspectives"] if item["role"] == "legal_risk")
    assert legal["evidence_ids"] == ["ev_legal"]
    assert "legal_documents" not in review["recommendation"]["required_confirmations"]
