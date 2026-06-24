import pytest

from agent_service.agents.market_analysis_agent import MarketAnalysisAgent
from agent_service.contracts import AgentAction, AgentContext
from agent_service.graph.charts import (
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
