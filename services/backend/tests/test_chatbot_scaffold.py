import importlib


def test_chatbot_graph_imports_as_experimental_scaffold():
    graph = importlib.import_module("chatbot.graph")

    assert hasattr(graph, "run_chat_pipeline")


def test_keyword_router_routes_legal_question_without_api_key(monkeypatch):
    router = importlib.import_module("chatbot.agents.router")
    monkeypatch.setattr(router, "GEMINI_API_KEY", "")

    result = router.router_node({"user_query": "Tu van phap ly khi mua nha"})

    assert result["intent"] == "legal_advice"
    assert result["target_agents"] == ["legal_advisor"]
    assert result["search_filters"] == {}


def test_keyword_router_routes_market_question_without_api_key(monkeypatch):
    router = importlib.import_module("chatbot.agents.router")
    monkeypatch.setattr(router, "GEMINI_API_KEY", "")

    result = router.router_node({"user_query": "Xu huong gia bat dong san nam nay"})

    assert result["intent"] == "market_analysis"
    assert result["target_agents"] == ["market_analysis"]
    assert result["search_filters"] == {}


def test_run_chat_pipeline_returns_public_contract(monkeypatch):
    graph = importlib.import_module("chatbot.graph")

    async def fake_ainvoke(initial_state):
        assert initial_state["user_query"] == "Tim nha quan 7"
        return {
            "final_response": "Ket qua thu nghiem",
            "sources": [{"id": 1}],
            "agent_used": "property_search",
            "suggested_actions": ["Xem them"],
        }

    monkeypatch.setattr(graph.chat_graph, "ainvoke", fake_ainvoke)

    import asyncio

    result = asyncio.run(graph.run_chat_pipeline("Tim nha quan 7"))

    assert result == {
        "final_response": "Ket qua thu nghiem",
        "sources": [{"id": 1}],
        "agent_used": "property_search",
        "suggested_actions": ["Xem them"],
    }
