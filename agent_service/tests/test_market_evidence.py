from __future__ import annotations

import pytest

from agent_service.graph import agentic_workflow as wf


@pytest.mark.asyncio
async def test_market_metrics_wrapper_emits_evidence_ids(monkeypatch):
    """Market metrics must expose evidence ids so grounded synthesis can cite
    market figures instead of always falling back to deterministic output."""

    async def fake_metrics(*, filters):
        return [
            {"source_identity": "market:Quận 1:all:avg_price_per_m2:current",
             "metric": "avg_price_per_m2", "value": 120.0},
            {"source_identity": "market:Quận 3:all:avg_price_per_m2:current",
             "metric": "avg_price_per_m2", "value": 95.0},
        ]

    monkeypatch.setattr("agent_service.tools.market.lookup_market_metrics", fake_metrics)
    registry = wf.build_default_tool_registry()

    out = await registry.call(
        tool_name="lookup_market_metrics",
        agent_name="market_analysis",
        filters={"city": "HCM"},
    )

    assert out["status"] == "success"
    assert out["evidence_ids"] == [
        "market:Quận 1:all:avg_price_per_m2:current",
        "market:Quận 3:all:avg_price_per_m2:current",
    ]


@pytest.mark.asyncio
async def test_market_timeseries_wrapper_emits_evidence_ids(monkeypatch):
    async def fake_timeseries(*, filters):
        return [
            {"snapshot_month": "2026-05", "city": "HCM", "district": "Quận 1",
             "property_type": "apartment", "avg_price_per_m2": 118.0},
            {"snapshot_month": "2026-06", "city": "HCM", "district": "Quận 1",
             "property_type": "apartment", "avg_price_per_m2": 121.0},
        ]

    monkeypatch.setattr("agent_service.tools.market.lookup_market_timeseries", fake_timeseries)
    registry = wf.build_default_tool_registry()

    out = await registry.call(
        tool_name="lookup_market_timeseries",
        agent_name="market_analysis",
        filters={"city": "HCM"},
    )

    assert out["status"] == "success"
    assert out["evidence_ids"] == [
        "market_ts:Quận 1:apartment:2026-05",
        "market_ts:Quận 1:apartment:2026-06",
    ]
