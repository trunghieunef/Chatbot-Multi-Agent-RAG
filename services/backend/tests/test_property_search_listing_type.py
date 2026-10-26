import pytest

from chatbot.agents import property_search


@pytest.mark.asyncio
async def test_property_search_forwards_listing_type(monkeypatch):
    captured = {}

    async def fake_hybrid(query, filters, parent_type):
        captured.update({"query": query, "filters": filters, "parent_type": parent_type})
        return []

    monkeypatch.setattr(property_search, "hybrid_search", fake_hybrid)

    state = {
        "user_query": "Cho thuê căn hộ Quận 7",
        "search_filters": {"listing_type": "rent", "district": "Quận 7"},
        "agent_results": {},
    }

    await property_search.property_search_node(state)

    assert captured["filters"]["listing_type"] == "rent"
    assert captured["filters"]["district"] == "Quận 7"
    assert captured["parent_type"] == "listing"
