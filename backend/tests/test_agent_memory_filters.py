from agent_service.graph.memory_filters import derive_memory_filters


def test_memory_fills_missing_district_without_overriding_query():
    result = derive_memory_filters(
        user_preferences={"preferred_district": "Quan 7"},
        current_filters={},
        query="tim can ho",
    )

    assert result.filters["district"] == "Quan 7"
    assert result.applied_keys == ["preferred_district"]
