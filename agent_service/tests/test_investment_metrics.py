from __future__ import annotations

from agent_service.graph.investment_model import calculate_investment_metrics


def _assumptions() -> dict:
    return {
        "purchase_price": {
            "value": 4.8,
            "unit": "billion_vnd",
            "source": "derived",
            "depends_on": ["ev_listing"],
            "evidence_ids": ["ev_listing"],
            "note": "",
        },
        "area": {
            "value": 75,
            "unit": "m2",
            "source": "derived",
            "depends_on": ["ev_listing"],
            "evidence_ids": ["ev_listing"],
            "note": "",
        },
        "loan_ratio": {
            "value": 0.6,
            "unit": "ratio_0_1",
            "source": "default",
            "depends_on": [],
            "evidence_ids": [],
            "note": "",
        },
        "interest_rate_annual": {
            "value": 0.1,
            "unit": "ratio_0_1",
            "source": "default",
            "depends_on": [],
            "evidence_ids": [],
            "note": "",
        },
        "loan_term_years": {
            "value": 20,
            "unit": "years",
            "source": "default",
            "depends_on": [],
            "evidence_ids": [],
            "note": "",
        },
        "expected_monthly_rent": {
            "value": 18_000_000,
            "unit": "vnd_per_month",
            "source": "user",
            "depends_on": [],
            "evidence_ids": [],
            "note": "",
        },
        "vacancy_months_per_year": {
            "value": 1,
            "unit": "months",
            "source": "default",
            "depends_on": [],
            "evidence_ids": [],
            "note": "",
        },
        "operating_cost_ratio": {
            "value": 0.08,
            "unit": "ratio_0_1",
            "source": "default",
            "depends_on": [],
            "evidence_ids": [],
            "note": "",
        },
    }


def test_calculate_metrics_includes_depends_on_and_core_values():
    metrics = calculate_investment_metrics(
        case={
            "market_summary": {
                "metric": "avg_price_per_m2",
                "value": 70,
                "unit": "million_vnd_per_m2",
                "evidence_ids": ["ev_market"],
            }
        },
        assumptions=_assumptions(),
    )

    assert metrics["price_per_m2"]["value"] == 64.0
    assert metrics["price_per_m2"]["unit"] == "million_vnd_per_m2"
    assert metrics["price_per_m2"]["depends_on"] == ["purchase_price", "area"]
    assert metrics["market_price_delta"]["value"] == -0.0857
    assert "ev_market" in metrics["market_price_delta"]["depends_on"]
    assert metrics["loan_amount"]["value"] == 2.88
    assert metrics["gross_yield"]["unit"] == "ratio_0_1"
    assert metrics["monthly_cashflow_estimate"]["depends_on"]


def test_missing_price_or_area_skips_dependent_metrics():
    assumptions = _assumptions()
    assumptions.pop("area")

    metrics = calculate_investment_metrics(case={}, assumptions=assumptions)

    assert "price_per_m2" not in metrics
    assert "market_price_delta" not in metrics
    assert "missing_area" in metrics["metric_warnings"]["warnings"]


def test_missing_purchase_price_skips_price_dependent_metrics():
    assumptions = _assumptions()
    assumptions.pop("purchase_price")

    metrics = calculate_investment_metrics(case={}, assumptions=assumptions)

    assert "price_per_m2" not in metrics
    assert "market_price_delta" not in metrics
    assert "loan_amount" not in metrics
    assert "monthly_payment_estimate" not in metrics
    assert "gross_yield" not in metrics
    assert "net_yield" not in metrics
    assert "monthly_cashflow_estimate" not in metrics
    assert "cash_on_cash_return" not in metrics
    assert "missing_purchase_price" in metrics["metric_warnings"]["warnings"]


def test_market_price_delta_prefers_primary_market_evidence_id():
    metrics = calculate_investment_metrics(
        case={
            "market_summary": {
                "metric": "avg_price_per_m2",
                "value": 70,
                "unit": "million_vnd_per_m2",
                "evidence_ids": ["ev_market_1", "ev_market_2"],
                "primary_evidence_id": "ev_market_1",
                "primary_evidence_ids": ["ev_market_1"],
                "items": [
                    {"evidence_id": "ev_market_1", "facts": {"value": 70}},
                    {"evidence_id": "ev_market_2", "facts": {"value": 72}},
                ],
            }
        },
        assumptions=_assumptions(),
    )

    assert metrics["market_price_delta"]["depends_on"] == [
        "price_per_m2",
        "ev_market_1",
    ]
