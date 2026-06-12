from agent_service.graph.query_understanding import merge_query_filters


def test_current_query_filter_overrides_llm_inferred_filter():
    deterministic = {"district": "Quan 7"}
    llm = {"district": "Quan 2", "max_price": 5000000000}

    merged = merge_query_filters(deterministic, llm)

    assert merged["district"] == "Quan 7"
    assert merged["max_price"] == 5000000000
