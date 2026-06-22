import pytest
from unittest.mock import AsyncMock, MagicMock

from agent_service.agents.property_search_agent import PropertySearchAgent
from agent_service.contracts import AgentContext
from agent_service.tools.registry import ToolRegistry, ToolDef


@pytest.fixture
def agent_context():
    return AgentContext(
        agent_name="property_search",
        query="Tìm căn hộ Quận 7 dưới 3 tỷ",
        normalized_query="tim can ho quan 7 duoi 3 ty",
        routing_filters={"city": "Hồ Chí Minh", "district": "Quận 7", "max_price": 3},
    )


@pytest.fixture
def tool_registry():
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="search_listings",
        description="Search real estate listings",
        parameters={"query": "str", "filters": "dict", "top_k": "int", "rerank_to": "int"},
        required_params=["query"],
        allowed_for=["property_search", "investment_advisor"],
    ))

    async def fake_search(*, query: str, filters: dict | None = None, top_k: int = 20, rerank_to: int = 5):
        return {
            "status": "success",
            "results": [
                {
                    "id": "L001",
                    "title": "Căn hộ cao cấp Quận 7",
                    "price_text": "2.5 tỷ",
                    "area_text": "70m²",
                    "district": "Quận 7",
                    "city": "Hồ Chí Minh",
                    "price_per_m2": 35.7,
                },
                {
                    "id": "L002",
                    "title": "Chung cư giá rẻ Quận 7",
                    "price_text": "2.8 tỷ",
                    "area_text": "75m²",
                    "district": "Quận 7",
                    "city": "Hồ Chí Minh",
                    "price_per_m2": 37.3,
                },
            ],
            "evidence_ids": ["ev_L001", "ev_L002"],
        }

    reg.bind("search_listings", fake_search)
    return reg


@pytest.mark.asyncio
async def test_property_search_agent_calls_search_listings(agent_context, tool_registry):
    agent = PropertySearchAgent(max_iterations=3)
    result = await agent.run(agent_context, {}, tool_registry=tool_registry)

    assert result.agent_name == "property_search"
    assert result.status == "completed"
    assert len(result.evidence_ids_used) >= 2
    assert "Quận 7" in result.content
    assert result.iterations >= 1


@pytest.mark.asyncio
async def test_property_search_agent_no_evidence(agent_context):
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="search_listings",
        description="Search listings",
        allowed_for=["property_search"],
    ))

    async def empty_search(*, query, filters=None, top_k=20, rerank_to=5):
        return {"status": "empty", "results": [], "evidence_ids": []}

    reg.bind("search_listings", empty_search)

    agent = PropertySearchAgent(max_iterations=3)
    result = await agent.run(agent_context, {}, tool_registry=reg)

    assert result.status in ("no_evidence", "partial", "completed")
    # Should not hallucinate listings when there are none
    assert "L001" not in result.content
