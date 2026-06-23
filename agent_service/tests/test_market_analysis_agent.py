import pytest

from agent_service.agents.market_analysis_agent import MarketAnalysisAgent
from agent_service.contracts import AgentContext
from agent_service.tools.registry import ToolDef, ToolRegistry


class FinalAnswerFirstLLM:
    async def generate_json(self, prompt: str, timeout_seconds: float = 15.0):
        return {
            "reasoning": "I can answer directly.",
            "action": "final_answer",
            "confidence": 0.9,
        }


@pytest.mark.asyncio
async def test_market_analysis_llm_guard_uses_tool_specific_params():
    captured_filters = []
    registry = ToolRegistry()
    registry.register(
        ToolDef(
            name="lookup_market_metrics",
            description="Lookup market metrics",
            parameters={"filters": "dict"},
            required_params=["filters"],
            allowed_for=["market_analysis"],
        )
    )

    async def lookup_market_metrics(*, filters):
        captured_filters.append(filters)
        return {
            "status": "success",
            "results": [
                {
                    "metric": "avg_price_per_m2",
                    "value": 72.5,
                    "unit": "million VND/m2",
                    "location": {"city": "Ho Chi Minh", "district": "Quan 7"},
                }
            ],
            "evidence_ids": [],
        }

    registry.bind("lookup_market_metrics", lookup_market_metrics)
    context = AgentContext(
        agent_name="market_analysis",
        query="Gia can ho Quan 7 the nao?",
        normalized_query="gia can ho quan 7 the nao?",
        routing_filters={"city": "Ho Chi Minh", "district": "Quan 7"},
    )

    agent = MarketAnalysisAgent(max_iterations=1, use_llm=True)
    result = await agent.run(
        context,
        {},
        tool_registry=registry,
        llm_client=FinalAnswerFirstLLM(),
    )

    assert result.status == "completed"
    assert captured_filters == [{"city": "Ho Chi Minh", "district": "Quan 7"}]
    assert "72.5" in result.content
