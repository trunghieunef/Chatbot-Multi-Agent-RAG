from __future__ import annotations

import pytest

from agent_service.agents import fc_runner
from agent_service.config import get_agent_settings
from agent_service.contracts import AgentContext, ToolDef
from agent_service.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_investment_uses_market_metrics_in_output():
    registry = ToolRegistry()
    registry.register(
        ToolDef(
            name="lookup_market_metrics",
            description="x",
            parameters={"filters": "dict"},
            required_params=["filters"],
            allowed_for=["investment_advisor"],
        )
    )

    calls = []

    async def metrics(**kwargs):
        calls.append(kwargs)
        return {
            "status": "success",
            "results": [
                {
                    "metric": "avg_price_per_m2",
                    "value": 50,
                    "unit": "million VND/m2",
                    "location": {"district": "Quận 7"},
                }
            ],
            "evidence_ids": [],
        }

    registry.bind("lookup_market_metrics", metrics)
    context = AgentContext(
        agent_name="investment_advisor",
        query="đầu tư căn hộ Quận 7",
        normalized_query="dau tu can ho quan 7",
        routing_filters={"city": "HCM", "district": "Quận 7"},
    )

    result = await fc_runner.run_specialist(
        agent_name="investment_advisor",
        context=context,
        registry=registry,
        llm_client=None,
        settings=get_agent_settings(),
    )

    assert result.status in {"completed", "no_evidence"}
    assert len(calls) == 1
    assert "50" in result.content or "Quận 7" in result.content
    assert "lời khuyên tài chính" in result.content.lower()
