import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent_service.agents.orchestrator import OrchestratorAgent
from agent_service.contracts import (
    AgentChatRequest,
    AgentChatResponse,
    ConversationContextItem,
)
from agent_service.tools.registry import ToolRegistry, ToolDef


@pytest.fixture
def chat_request():
    return AgentChatRequest(
        request_id="test-001",
        message="Tìm căn hộ Quận 7 dưới 3 tỷ",
        session_id="sess-001",
    )


@pytest.fixture
def tool_registry():
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="search_listings",
        description="Search listings",
        allowed_for=["property_search", "investment_advisor"],
    ))

    async def fake_search(*, query, filters=None, top_k=20, rerank_to=5):
        return {
            "status": "success",
            "results": [
                {"id": "L001", "title": "Căn hộ Quận 7", "price_text": "2.5 tỷ",
                 "area_text": "70m²", "district": "Quận 7", "city": "Hồ Chí Minh"},
            ],
            "evidence_ids": ["ev_L001"],
        }

    reg.bind("search_listings", fake_search)
    return reg


@pytest.mark.asyncio
async def test_orchestrator_routes_and_dispatches(chat_request, tool_registry):
    orchestrator = OrchestratorAgent(tool_registry=tool_registry)
    response = await orchestrator.run(chat_request)

    assert isinstance(response, AgentChatResponse)
    assert response.request_id == "test-001"
    assert len(response.agents_used) >= 1
    assert "property_search" in response.agents_used
    assert len(response.final_response) > 0


@pytest.mark.asyncio
async def test_orchestrator_handles_empty_query():
    req = AgentChatRequest(
        request_id="test-002",
        message=" ",
        session_id="sess-002",
    )
    orchestrator = OrchestratorAgent(tool_registry=ToolRegistry())
    response = await orchestrator.run(req)

    assert response.request_id == "test-002"
    assert len(response.final_response) > 0
