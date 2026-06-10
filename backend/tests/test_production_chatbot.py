import asyncio
from types import SimpleNamespace

import pytest

from app.services.chatbot.agents.property import run_property_search
from app.services.chatbot.agents.legal import run_legal_advisor
from app.services.chatbot.agents.market import run_market_analysis
from app.services.chatbot.agents.investment import run_investment_advisor
from app.services.chatbot.contracts import AgentResult
from app.services.chatbot.orchestrator import run_chat_pipeline
from app.services.chatbot.router import route_query


def test_route_query_selects_multiple_agents_and_extracts_filters(monkeypatch):
    import app.services.chatbot.router as router

    monkeypatch.setattr(router, "get_settings", lambda: SimpleNamespace(GEMINI_API_KEY=""))

    decision = route_query("Mua can ho Quan 7 de dau tu duoi 5 ty")

    assert decision.intent == "mixed"
    assert decision.target_agents == ["investment_advisor", "property_search"]
    assert decision.search_filters["listing_type"] == "sale"
    assert decision.search_filters["district"] == "Quan 7"
    assert decision.search_filters["max_price"] == 5


def test_route_query_honors_rule_intent_extractor_when_gemini_key_exists(monkeypatch):
    import sys
    import types

    import app.services.chatbot.router as router

    called = {"gemini": False}

    google_module = types.ModuleType("google")
    genai_module = types.ModuleType("google.genai")
    genai_types_module = types.ModuleType("google.genai.types")

    class FakeResponse:
        text = '{"intent":"property_search","target_agents":["property_search"],"search_filters":{}}'

    class FakeModels:
        def generate_content(self, *_, **__):
            return FakeResponse()

    class FakeClient:
        def __init__(self, *_, **__):
            called["gemini"] = True
            self.models = FakeModels()

    class FakeGenerateContentConfig:
        def __init__(self, *_, **__):
            pass

    genai_module.Client = FakeClient
    genai_module.types = genai_types_module
    genai_types_module.GenerateContentConfig = FakeGenerateContentConfig
    google_module.genai = genai_module

    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.genai", genai_module)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai_types_module)
    monkeypatch.setattr(
        router,
        "get_settings",
        lambda: SimpleNamespace(GEMINI_API_KEY="test-key", INTENT_EXTRACTOR="rule"),
    )

    decision = route_query("Mua can ho Quan 7 duoi 5 ty")

    assert called["gemini"] is False
    assert decision.intent == "property_search"
    assert decision.search_filters["district"] == "Quan 7"
    assert decision.search_filters["max_price"] == 5


def test_route_query_selects_legal_agent_for_legal_question(monkeypatch):
    import app.services.chatbot.router as router

    monkeypatch.setattr(router, "get_settings", lambda: SimpleNamespace(GEMINI_API_KEY=""))

    decision = route_query("Tu van phap ly sang ten so do khi mua nha")

    assert decision.intent == "legal_advice"
    assert decision.target_agents == ["legal_advisor"]


def test_legal_agent_returns_disclaimer_and_sources():
    result = asyncio.run(run_legal_advisor("Can kiem tra gi truoc khi dat coc?", db=None, routing=None))

    assert result.agent_name == "legal_advisor"
    assert "tham khao" in result.content.lower()
    assert result.sources
    assert result.suggested_actions


@pytest.mark.asyncio
async def test_property_agent_uses_chunk_hybrid_search(monkeypatch):
    from app.services.chatbot import contracts
    from app.services.chatbot.agents import property as property_agent

    called = {}

    async def fake_hybrid_search(query, filters=None, parent_type="listing", top_k=20, rerank_to=5):
        called["query"] = query
        called["filters"] = filters
        called["parent_type"] = parent_type
        return [
            {
                "id": 7,
                "product_id": "hf-7",
                "title": "Can ho Quan 7",
                "price_text": "4.8 ty",
                "area_text": "70 m2",
                "district": "Quan 7",
                "city": "Ho Chi Minh",
                "url": "https://example.test/hf-7",
                "matched_chunk": {"distance": 0.1234},
            }
        ]

    monkeypatch.setattr(property_agent, "hybrid_search", fake_hybrid_search, raising=False)
    routing = contracts.RoutingDecision(
        intent="property_search",
        target_agents=["property_search"],
        search_filters={"district": "Quan 7"},
    )

    result = await run_property_search("Tim can ho Quan 7", db=object(), routing=routing)

    assert called == {
        "query": "Tim can ho Quan 7",
        "filters": {"district": "Quan 7"},
        "parent_type": "listing",
    }
    assert result.agent_name == "property_search"
    assert "Can ho Quan 7" in result.content
    assert result.sources[0]["product_id"] == "hf-7"
    assert result.sources[0]["type"] == "listing"
    assert result.suggested_actions


@pytest.mark.asyncio
async def test_legal_agent_uses_legal_kb_when_chunks_exist(monkeypatch):
    from app.services.chatbot.agents import legal as legal_agent

    async def fake_hybrid_search(query, filters=None, parent_type="article", top_k=20, rerank_to=5):
        assert parent_type == "article"
        assert filters["category"] == "legal"
        return [
            {
                "id": 3,
                "title": "Luat Dat dai 2024",
                "category": "legal",
                "source": "luat-dat-dai-2024.pdf",
                "url": None,
                "citation": {
                    "doc_slug": "luat-dat-dai-2024",
                    "dieu_number": 45,
                    "khoan_number": 1,
                },
                "matched_chunk": {
                    "text": "Dieu 45 quy dinh ve dieu kien chuyen nhuong quyen su dung dat.",
                    "distance": 0.2,
                },
            }
        ]

    monkeypatch.setattr(legal_agent, "hybrid_search", fake_hybrid_search, raising=False)

    result = await run_legal_advisor("Dieu kien sang ten so do la gi?", db=None, routing=None)

    assert result.agent_name == "legal_advisor"
    assert "luat-dat-dai-2024" in result.content
    assert "Dieu 45" in result.content
    assert result.sources[0]["type"] == "legal_article"
    assert result.sources[0]["citation"]["dieu_number"] == 45


@pytest.mark.asyncio
async def test_market_agent_includes_district_comparison(monkeypatch):
    from app.services.chatbot.agents import market as market_agent
    from app.services.chatbot import contracts

    async def fake_market_snapshot(db, filters):
        return {
            "count": 25,
            "avg_price": 4.2,
            "avg_area": 68.0,
            "avg_price_per_m2": 61.5,
        }

    async def fake_district_comparison(db, filters, limit=5):
        return [
            {"district": "Quan 7", "count": 12, "avg_price": 4.0, "avg_price_per_m2": 58.0},
            {"district": "Quan 2", "count": 8, "avg_price": 5.1, "avg_price_per_m2": 72.0},
        ]

    monkeypatch.setattr(market_agent, "get_market_snapshot", fake_market_snapshot, raising=False)
    monkeypatch.setattr(market_agent, "get_district_comparison", fake_district_comparison, raising=False)

    routing = contracts.RoutingDecision(
        intent="market_analysis",
        target_agents=["market_analysis"],
        search_filters={"city": "Ho Chi Minh", "listing_type": "sale"},
    )

    result = await run_market_analysis("So sanh gia cac quan", db=object(), routing=routing)

    assert "Quan 7" in result.content
    assert "Quan 2" in result.content
    assert result.sources[0]["type"] == "market_aggregate"
    assert result.sources[1]["type"] == "district_comparison"


@pytest.mark.asyncio
async def test_investment_agent_estimates_rental_yield(monkeypatch):
    from app.services.chatbot.agents import investment as investment_agent
    from app.services.chatbot import contracts

    async def fake_market_snapshot(db, filters):
        if filters.get("listing_type") == "rent":
            return {"count": 10, "avg_price": 18.0, "avg_area": 70.0, "avg_price_per_m2": 0.25}
        return {"count": 12, "avg_price": 4.8, "avg_area": 70.0, "avg_price_per_m2": 68.0}

    monkeypatch.setattr(investment_agent, "get_market_snapshot", fake_market_snapshot, raising=False)

    routing = contracts.RoutingDecision(
        intent="investment_advice",
        target_agents=["investment_advisor"],
        search_filters={"district": "Quan 7"},
    )

    result = await run_investment_advisor("Dau tu can ho Quan 7", db=object(), routing=routing)

    assert "rental yield" in result.content.lower()
    assert "4.5%" in result.content
    assert result.sources[0]["type"] == "investment_aggregate"


def test_run_chat_pipeline_combines_agent_results(monkeypatch):
    async def fake_property(query, db, routing):
        return AgentResult(
            agent_name="property_search",
            content="Found matching listings.",
            sources=[{"product_id": "hf-1", "title": "Listing 1"}],
            suggested_actions=["Compare listings"],
            confidence=0.9,
        )

    async def fake_market(query, db, routing):
        return AgentResult(
            agent_name="market_analysis",
            content="Market is active.",
            sources=[],
            suggested_actions=["View market stats"],
            confidence=0.8,
        )

    import app.services.chatbot.orchestrator as orchestrator

    monkeypatch.setattr(
        orchestrator,
        "AGENT_RUNNERS",
        {
            "property_search": fake_property,
            "market_analysis": fake_market,
        },
    )

    result = asyncio.run(run_chat_pipeline("Tim nha va xem thi truong", db=object()))

    assert result["agent_used"] == "market_analysis, property_search"
    assert "Found matching listings." in result["final_response"]
    assert "Market is active." in result["final_response"]
    assert result["sources"] == [{"product_id": "hf-1", "title": "Listing 1"}]
    assert result["suggested_actions"] == ["View market stats", "Compare listings"]
