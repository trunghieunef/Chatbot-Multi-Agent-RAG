import pytest

from agent_service.agents.market_analysis_agent import MarketAnalysisAgent
from agent_service.contracts import AgentAction, AgentContext
from agent_service.graph.agentic_workflow import _collect_charts
from agent_service.graph.charts import (
    build_comparison_table,
    build_district_comparison_chart,
    build_price_trend_chart,
)


def test_price_trend_builds_sorted_line_band():
    rows = [
        {"snapshot_month": "2024-Q4", "avg_price_per_m2": 78, "min_price_per_m2": 60, "max_price_per_m2": 95},
        {"snapshot_month": "2024-Q2", "avg_price_per_m2": 70, "min_price_per_m2": 55, "max_price_per_m2": 88},
    ]
    chart = build_price_trend_chart(rows, title="T")
    assert chart["type"] == "line_band"
    assert chart["x_key"] == "month"
    assert [d["month"] for d in chart["data"]] == ["2024-Q2", "2024-Q4"]
    assert chart["data"][0] == {"month": "2024-Q2", "avg": 70.0, "min": 55.0, "max": 88.0}


def test_price_trend_none_under_two_points():
    assert build_price_trend_chart([{"snapshot_month": "a", "avg_price_per_m2": 78}], title="T") is None
    assert build_price_trend_chart([], title="T") is None


def test_price_trend_skips_rows_without_numeric_avg():
    rows = [
        {"snapshot_month": "a", "avg_price_per_m2": None},
        {"snapshot_month": "b", "avg_price_per_m2": 70, "min_price_per_m2": 55, "max_price_per_m2": 90},
        {"snapshot_month": "c", "avg_price_per_m2": 80, "min_price_per_m2": 60, "max_price_per_m2": 100},
    ]
    chart = build_price_trend_chart(rows, title="T")
    assert [d["month"] for d in chart["data"]] == ["b", "c"]


def test_district_comparison_sorted_desc():
    metrics = [
        {"metric": "avg_price_per_m2", "value": 105, "location": {"district": "Cầu Giấy"}},
        {"metric": "avg_price_per_m2", "value": 120, "location": {"district": "Đống Đa"}},
    ]
    chart = build_district_comparison_chart(metrics, title="T")
    assert chart["type"] == "bar"
    assert chart["x_key"] == "district"
    assert [d["district"] for d in chart["data"]] == ["Đống Đa", "Cầu Giấy"]
    assert chart["data"][0] == {"district": "Đống Đa", "avg": 120.0}


def test_district_comparison_none_under_two_and_dedups():
    one = [{"metric": "avg_price_per_m2", "value": 120, "location": {"district": "A"}}]
    assert build_district_comparison_chart(one, title="T") is None
    dup = [
        {"metric": "avg_price_per_m2", "value": 120, "location": {"district": "Đống Đa"}},
        {"metric": "avg_price_per_m2", "value": 118, "location": {"district": "Đống Đa"}},
        {"metric": "avg_price_per_m2", "value": 105, "location": {"district": "Cầu Giấy"}},
    ]
    chart = build_district_comparison_chart(dup, title="T")
    assert len(chart["data"]) == 2
    assert chart["data"][0] == {"district": "Đống Đa", "avg": 120.0}


@pytest.mark.asyncio
async def test_market_agent_build_result_emits_charts():
    ctx = AgentContext(
        agent_name="market_analysis",
        query="giá Đống Đa đang tăng hay giảm",
        routing_filters={"district": "Đống Đa", "city": "Hà Nội", "property_type": "Căn hộ chung cư"},
    )
    action = AgentAction(
        iteration=1,
        action_type="call_tool",
        status="success",
        tool_result={
            "results": [
                {"snapshot_month": "2024-Q2", "avg_price_per_m2": 70, "min_price_per_m2": 55, "max_price_per_m2": 88},
                {"snapshot_month": "2024-Q4", "avg_price_per_m2": 78, "min_price_per_m2": 60, "max_price_per_m2": 95},
                {"metric": "avg_price_per_m2", "value": 120, "location": {"district": "Đống Đa"}},
                {"metric": "avg_price_per_m2", "value": 105, "location": {"district": "Cầu Giấy"}},
            ]
        },
    )
    result = MarketAnalysisAgent().build_result(ctx, thoughts=[], actions=[action])
    types = {c["type"] for c in result.charts}
    assert types == {"line_band", "bar"}
    trend = next(c for c in result.charts if c["type"] == "line_band")
    assert "Đống Đa" in trend["title"]


def test_market_agent_no_charts_without_data():
    ctx = AgentContext(agent_name="market_analysis", query="x")
    action = AgentAction(iteration=1, action_type="call_tool", status="success", tool_result={"results": []})
    result = MarketAnalysisAgent().build_result(ctx, thoughts=[], actions=[action])
    assert result.charts == []


def test_collect_charts_gathers_only_used_agents():
    raw = {
        "market_analysis": {"charts": [{"type": "bar"}, {"type": "line_band"}]},
        "property_search": {"charts": [{"type": "ignored"}]},
    }
    assert _collect_charts(raw, ["market_analysis"]) == [{"type": "bar"}, {"type": "line_band"}]


def test_collect_charts_handles_missing_and_nonlist():
    assert _collect_charts({}, ["market_analysis"]) == []
    assert _collect_charts({"market_analysis": {}}, ["market_analysis"]) == []
    assert _collect_charts({"market_analysis": {"charts": 42}}, ["market_analysis"]) == []


def test_comparison_table_tags_ppm_and_pct():
    listings = [
        {"id": 1, "title": "A", "url": "/a", "price": 6.6, "area": 79,
         "price_text": "6,6 tỷ", "area_text": "79 m²", "bedrooms": 3, "bathrooms": 2,
         "legal_status": "Sổ đỏ", "furniture": "Đầy đủ", "district": "Nam Từ Liêm", "city": "Hà Nội"},
        {"id": 2, "title": "B", "url": "/b", "price": 3.9, "area": 55,
         "price_text": "3,9 tỷ", "area_text": "55 m²", "bedrooms": 2, "bathrooms": 1,
         "district": "Nam Từ Liêm", "city": "Hà Nội"},
    ]
    table = build_comparison_table(listings, area_avg_price_per_m2=100.0)
    assert table["type"] == "comparison_table"
    assert table["title"] == "So sánh 2 căn"
    rows = table["rows"]
    assert rows[0]["price_per_m2"] == 83.5   # 6.6*1000/79
    assert rows[1]["price_per_m2"] == 70.9   # 3.9*1000/55
    assert rows[0]["location"] == "Nam Từ Liêm, Hà Nội"
    assert "Rộng nhất" in rows[0]["tags"]
    assert "Rẻ nhất" in rows[1]["tags"]
    assert "Giá/m² tốt nhất" in rows[1]["tags"]
    assert rows[0]["pct_vs_area_avg"] == -16.5
    assert rows[1]["pct_vs_area_avg"] == -29.1


def test_comparison_table_none_under_two():
    assert build_comparison_table([{"id": 1, "price": 5, "area": 50}], area_avg_price_per_m2=100.0) is None
    assert build_comparison_table([], area_avg_price_per_m2=None) is None


def test_comparison_table_missing_price_area_and_no_avg():
    listings = [
        {"id": 1, "title": "A", "price": None, "area": None, "price_text": "Liên hệ", "area_text": "N/A"},
        {"id": 2, "title": "B", "price": 4.0, "area": 50, "price_text": "4 tỷ", "area_text": "50 m²"},
    ]
    table = build_comparison_table(listings, area_avg_price_per_m2=None)
    assert table["rows"][0]["price_per_m2"] is None
    assert table["rows"][0]["pct_vs_area_avg"] is None
    assert table["rows"][1]["pct_vs_area_avg"] is None   # no avg
    assert table["rows"][0]["url"] == "/nha-dat-ban/1"   # url fallback from id
    assert "Rẻ nhất" in table["rows"][1]["tags"]         # only B has a numeric price


def test_comparison_table_auto_open_flag():
    listings = [
        {"id": 1, "title": "A", "price": 6.6, "area": 79},
        {"id": 2, "title": "B", "price": 3.9, "area": 55},
    ]
    assert build_comparison_table(listings, area_avg_price_per_m2=None)["auto_open"] is False
    assert build_comparison_table(listings, area_avg_price_per_m2=None, auto_open=True)["auto_open"] is True


def test_comparison_table_zero_price_is_not_missing():
    listings = [
        {"id": 1, "title": "A", "price": 0.0, "area": 50},
        {"id": 2, "title": "B", "price": 4.0, "area": 50},
    ]
    table = build_comparison_table(listings, area_avg_price_per_m2=None)
    assert table["rows"][0]["price_per_m2"] == 0.0   # zero price computed, not None


from agent_service.agents.property_search_agent import PropertySearchAgent


def _ps_action(results):
    return AgentAction(iteration=1, action_type="call_tool", status="success",
                       tool_result={"results": results})


def test_property_search_emits_comparison_table():
    ctx = AgentContext(agent_name="property_search", query="tìm căn hộ")
    listings = [
        {"id": 1, "title": "A", "price": 6.6, "area": 79, "price_text": "6,6 tỷ", "area_text": "79 m²"},
        {"id": 2, "title": "B", "price": 3.9, "area": 55, "price_text": "3,9 tỷ", "area_text": "55 m²"},
    ]
    result = PropertySearchAgent().build_result(ctx, thoughts=[], actions=[_ps_action(listings)])
    tables = [c for c in result.charts if c.get("type") == "comparison_table"]
    assert len(tables) == 1
    assert len(tables[0]["rows"]) == 2


def test_property_search_no_table_for_single_listing():
    ctx = AgentContext(agent_name="property_search", query="tìm căn hộ")
    listings = [{"id": 1, "title": "A", "price": 6.6, "area": 79, "price_text": "6,6 tỷ", "area_text": "79 m²"}]
    result = PropertySearchAgent().build_result(ctx, thoughts=[], actions=[_ps_action(listings)])
    assert result.charts == []


def test_property_search_auto_opens_table_on_compare_intent():
    listings = [
        {"id": 1, "title": "A", "price": 6.6, "area": 79, "price_text": "6,6 tỷ", "area_text": "79 m²"},
        {"id": 2, "title": "B", "price": 3.9, "area": 55, "price_text": "3,9 tỷ", "area_text": "55 m²"},
    ]
    # Plain search -> button collapsed
    plain = PropertySearchAgent().build_result(
        AgentContext(agent_name="property_search", query="tìm căn hộ Nam Từ Liêm"),
        thoughts=[], actions=[_ps_action(listings)],
    )
    assert plain.charts[0]["auto_open"] is False
    # Explicit compare request -> table auto-opens
    compare = PropertySearchAgent().build_result(
        AgentContext(agent_name="property_search", query="so sánh các căn này"),
        thoughts=[], actions=[_ps_action(listings)],
    )
    assert compare.charts[0]["auto_open"] is True
