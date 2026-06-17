from __future__ import annotations

from agent_service.graph.query_understanding import validate_filters


def test_query_understanding_preserves_investment_user_inputs():
    filters = validate_filters(
        {
            "district": "Quan 7",
            "expected_monthly_rent": 18_000_000,
            "loan_ratio": 0.7,
            "interest_rate_annual": 0.095,
            "unsupported": "drop",
        }
    )

    assert filters == {
        "district": "Quan 7",
        "expected_monthly_rent": 18_000_000,
        "loan_ratio": 0.7,
        "interest_rate_annual": 0.095,
    }
