from __future__ import annotations

from agent_service.contracts import AgentSource, Evidence
from agent_service.graph.investment_model import (
    build_investment_case,
    resolve_investment_assumptions,
)


def _evidence(
    evidence_id: str,
    *,
    domain: str,
    facts: dict,
    source_type: str = "listing",
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        retrieval_task_id=f"task_{domain}",
        domain=domain,
        source_type=source_type,
        source_identity=f"{source_type}:{evidence_id}",
        record={},
        facts=facts,
        source=AgentSource(
            type=source_type,
            domain=domain,
            id=evidence_id,
            title=str(facts.get("title") or facts.get("metric") or evidence_id),
        ),
        retrieved_for=["investment_advisor"],
        assigned_to=["investment_advisor"],
    )


def test_build_investment_case_keeps_evidence_back_links():
    evidence_by_id = {
        "ev_listing": _evidence(
            "ev_listing",
            domain="property",
            facts={
                "title": "Can ho Quan 7",
                "price": 4.8,
                "area": 75,
                "price_text": "4.8 ty",
                "area_text": "75 m2",
                "location": {"district": "Quan 7", "city": "Ho Chi Minh"},
            },
        ),
        "ev_market": _evidence(
            "ev_market",
            domain="market",
            source_type="market_metric",
            facts={
                "metric": "avg_price_per_m2",
                "value": 70,
                "unit": "million_vnd_per_m2",
                "location": {"district": "Quan 7"},
            },
        ),
    }
    case = build_investment_case(
        evidence_by_id=evidence_by_id,
        evidence_for_agent={"investment_advisor": ["ev_listing", "ev_market"]},
    )

    assert case["case_scope"] == "single_listing"
    assert case["property_summary"]["evidence_ids"] == ["ev_listing"]
    assert case["market_summary"]["evidence_ids"] == ["ev_market"]
    assert sorted(case["evidence_ids"]) == ["ev_listing", "ev_market"]


def test_resolve_assumptions_uses_user_values_then_defaults_with_ratio_units():
    case = {
        "property_summary": {
            "price": 4.8,
            "area": 75,
            "evidence_ids": ["ev_listing"],
        }
    }
    assumptions = resolve_investment_assumptions(
        case=case,
        user_inputs={"loan_ratio": 0.7, "expected_monthly_rent": 18_000_000},
        preferences={"interest_rate_annual": {"value": 0.095}},
    )

    assert assumptions["loan_ratio"]["value"] == 0.7
    assert assumptions["loan_ratio"]["unit"] == "ratio_0_1"
    assert assumptions["loan_ratio"]["source"] == "user"
    assert assumptions["interest_rate_annual"]["value"] == 0.095
    assert assumptions["interest_rate_annual"]["source"] == "preference"
    assert assumptions["operating_cost_ratio"]["value"] == 0.08
    assert assumptions["operating_cost_ratio"]["source"] == "default"
    assert assumptions["purchase_price"]["source"] == "derived"
    assert assumptions["purchase_price"]["depends_on"] == ["ev_listing"]


def test_resolve_assumptions_derives_equity_ratio_from_user_loan_ratio():
    assumptions = resolve_investment_assumptions(
        case={"property_summary": {}},
        user_inputs={"loan_ratio": 0.7},
        preferences={},
    )

    assert assumptions["loan_ratio"]["value"] == 0.7
    assert assumptions["loan_ratio"]["source"] == "user"
    assert assumptions["equity_ratio"]["value"] == 0.3
    assert assumptions["equity_ratio"]["unit"] == "ratio_0_1"
    assert assumptions["equity_ratio"]["source"] == "derived"
    assert assumptions["equity_ratio"]["depends_on"] == ["loan_ratio"]


def test_build_investment_case_preserves_items_for_multi_evidence_summary():
    evidence_by_id = {
        "ev_market_1": _evidence(
            "ev_market_1",
            domain="market",
            source_type="market_metric",
            facts={"metric": "avg_price_per_m2", "value": 70},
        ),
        "ev_market_2": _evidence(
            "ev_market_2",
            domain="market",
            source_type="market_metric",
            facts={"metric": "liquidity_score", "value": "medium"},
        ),
    }

    case = build_investment_case(
        evidence_by_id=evidence_by_id,
        evidence_for_agent={"investment_advisor": ["ev_market_1", "ev_market_2"]},
    )

    assert case["market_summary"]["evidence_ids"] == ["ev_market_1", "ev_market_2"]
    assert case["market_summary"]["primary_evidence_id"] == "ev_market_1"
    assert case["market_summary"]["primary_evidence_ids"] == ["ev_market_1"]
    assert len(case["market_summary"]["items"]) == 2
    assert case["market_summary"]["items"][0] == {
        "evidence_id": "ev_market_1",
        "facts": {"metric": "avg_price_per_m2", "value": 70},
        "source_type": "market_metric",
    }


def test_build_investment_case_respects_explicit_empty_investment_assignment():
    evidence_by_id = {
        "ev_listing": _evidence(
            "ev_listing",
            domain="property",
            facts={"title": "Can ho Quan 7", "price": 4.8, "area": 75},
        )
    }

    case = build_investment_case(
        evidence_by_id=evidence_by_id,
        evidence_for_agent={"investment_advisor": []},
    )

    assert case["evidence_ids"] == []
    assert "property" in case["missing_evidence"]
