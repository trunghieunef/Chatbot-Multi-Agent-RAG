"""End-to-end tests for the Agentic RAG pipeline.

These tests exercise the full routing → dispatch → synthesis flow
using the ToolRegistry with mock tool bindings (no DB required).

Run with: python -m pytest agent_service/tests/test_agentic_e2e.py -v
"""

import pytest
from agent_service.contracts import AgentChatRequest
from agent_service.graph.agentic_workflow import run_agentic_graph
from agent_service.tools.registry import ToolRegistry, ToolDef
from agent_service.graph.agentic_workflow import _agentic_registry


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the singleton registry before each test."""
    import agent_service.graph.agentic_workflow as mod
    mod._agentic_registry = None
    yield
    mod._agentic_registry = None


@pytest.fixture
def seeded_registry():
    """Build a registry with fake tool bindings for testing."""
    import agent_service.graph.agentic_workflow as mod
    reg = ToolRegistry()

    reg.register(ToolDef(
        name="search_listings",
        description="Search listings",
        allowed_for=["property_search", "investment_advisor"],
    ))
    reg.register(ToolDef(
        name="search_articles",
        description="Search articles",
        allowed_for=["legal_advisor", "news_agent"],
    ))
    reg.register(ToolDef(
        name="search_projects",
        description="Search projects",
        allowed_for=["project_agent"],
    ))
    reg.register(ToolDef(
        name="lookup_market_metrics",
        description="Market metrics",
        allowed_for=["market_analysis", "investment_advisor", "property_search"],
    ))
    reg.register(ToolDef(
        name="lookup_market_timeseries",
        description="Market timeseries",
        allowed_for=["market_analysis", "investment_advisor"],
    ))

    async def fake_listings(*, query, filters=None, top_k=20, rerank_to=5):
        return {
            "status": "success",
            "results": [
                {"id": "L001", "title": "Căn hộ Q7", "price_text": "2.5 tỷ",
                 "area_text": "70m²", "district": "Quận 7", "city": "Hồ Chí Minh"},
            ],
            "evidence_ids": ["ev_L001"],
        }

    async def fake_articles(*, query, filters=None, top_k=20, rerank_to=5):
        return {
            "status": "success",
            "results": [
                {"id": "A001", "title": "Thủ tục sang tên sổ đỏ",
                 "citation": "Luật Đất đai 2024", "snippet": "Cần chuẩn bị..."},
            ],
            "evidence_ids": ["ev_A001"],
        }

    async def fake_projects(*, query, filters=None, top_k=20, rerank_to=5):
        return {
            "status": "success",
            "results": [
                {"id": "P001", "title": "Dự án ABC", "developer": "Cty XYZ",
                 "location": "Quận 2, Hồ Chí Minh"},
            ],
            "evidence_ids": ["ev_P001"],
        }

    async def fake_metrics(*, filters):
        return {
            "status": "success",
            "results": [
                {"metric": "avg_price_per_m2", "value": 45.0, "unit": "tr/m²",
                 "location": {"district": "Quận 7"}, "period": "current"},
            ],
            "evidence_ids": [],
        }

    async def fake_timeseries(*, filters):
        return {
            "status": "success",
            "results": [
                {"snapshot_month": "2026-05", "avg_price_per_m2": 44.0},
                {"snapshot_month": "2026-06", "avg_price_per_m2": 45.0},
            ],
            "evidence_ids": [],
        }

    reg.bind("search_listings", fake_listings)
    reg.bind("search_articles", fake_articles)
    reg.bind("search_projects", fake_projects)
    reg.bind("lookup_market_metrics", fake_metrics)
    reg.bind("lookup_market_timeseries", fake_timeseries)

    mod._agentic_registry = reg
    return reg


@pytest.mark.asyncio
async def test_agentic_e2e_property_search(seeded_registry):
    """Full end-to-end: routing → agent dispatch → synthesis."""
    request = AgentChatRequest(
        request_id="e2e-001",
        message="Tìm căn hộ Quận 7 dưới 3 tỷ",
        session_id="e2e-sess",
    )
    response = await run_agentic_graph(request)

    assert response.request_id == "e2e-001"
    assert len(response.final_response) > 10
    assert "property_search" in response.agents_used
    assert response.final_response != ""


@pytest.mark.asyncio
async def test_agentic_e2e_legal_question(seeded_registry):
    request = AgentChatRequest(
        request_id="e2e-002",
        message="Thủ tục sang tên sổ đỏ cần những giấy tờ gì?",
        session_id="e2e-sess",
    )
    response = await run_agentic_graph(request)

    assert response.request_id == "e2e-002"
    assert len(response.final_response) > 10
    assert "legal_advisor" in response.agents_used


@pytest.mark.asyncio
async def test_agentic_e2e_empty_query(seeded_registry):
    """Empty-ish query should get a helpful fallback response."""
    request = AgentChatRequest(
        request_id="e2e-004",
        message=" ",
        session_id="e2e-sess",
    )
    response = await run_agentic_graph(request)

    assert response.request_id == "e2e-004"
    assert len(response.final_response) > 10
    assert len(response.suggested_actions) > 0
