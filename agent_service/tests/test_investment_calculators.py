from __future__ import annotations

import pytest

from agent_service.agents.specialists import (
    _investment_calculations,
    run_investment_agent,
)


def test_investment_calculations_compute_price_per_m2_delta():
    calculations = _investment_calculations(
        property_evidence=[
            {
                "facts": {
                    "title": "Can ho Quan 7",
                    "price": 4.8,
                    "area": 75,
                    "location": {"district": "Quan 7", "city": "Ho Chi Minh"},
                }
            }
        ],
        market_evidence=[
            {
                "facts": {
                    "metric": "avg_price_per_m2",
                    "value": 70,
                    "unit": "million VND/m2",
                }
            }
        ],
    )

    assert calculations[0]["listing_price_per_m2_million"] == 64.0
    assert calculations[0]["market_delta_percent"] == -8.57


@pytest.mark.asyncio
async def test_investment_agent_mentions_price_per_m2_when_available():
    result = await run_investment_agent(
        query="Co nen dau tu can ho nay khong?",
        evidence=[
            {
                "evidence_id": "ev_listing",
                "domain": "property",
                "facts": {
                    "title": "Can ho Quan 7",
                    "price": 4.8,
                    "area": 75,
                },
            },
            {
                "evidence_id": "ev_market",
                "domain": "market",
                "source_type": "market_metric",
                "facts": {
                    "metric": "avg_price_per_m2",
                    "value": 70,
                    "unit": "million VND/m2",
                },
            },
        ],
        preferences={},
        readiness={"listings": {"status": "ready"}},
    )

    assert "64.0 trieu/m2" in result["content"]
    assert "chenh lech -8.57%" in result["content"]
