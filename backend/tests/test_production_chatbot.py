import asyncio
from types import SimpleNamespace

from app.services.chatbot.agents.legal import run_legal_advisor
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
