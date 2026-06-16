from __future__ import annotations

from agent_service.graph.memory_extraction import extract_memory_proposals


def test_extract_memory_proposals_from_query_and_filters():
    proposals = extract_memory_proposals(
        query="Toi muon mua can ho 2 phong ngu o Quan 7 duoi 5 ty",
        filters={
            "listing_type": "sale",
            "property_type": "Can ho",
            "district": "Quan 7",
            "max_price": 5.0,
            "bedrooms": 2,
        },
    )

    by_key = {proposal.key: proposal.value for proposal in proposals}

    assert by_key["listing_type"] == "sale"
    assert by_key["preferred_property_type"] == "Can ho"
    assert by_key["preferred_district"] == "Quan 7"
    assert by_key["max_budget"] == 5.0
    assert by_key["bedrooms"] == 2


def test_extract_memory_proposals_ignores_empty_filters():
    assert extract_memory_proposals(query="Xin chao", filters={}) == []
