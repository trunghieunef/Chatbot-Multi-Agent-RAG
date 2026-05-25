"""
Market Analysis Agent — Analyze real estate market trends and statistics.

Queries PostgreSQL aggregations for price trends, supply/demand,
and regional comparisons.
"""

from chatbot.state import ChatState
from chatbot.tools.market_stats import district_price_overview


async def market_analysis_node(state: ChatState) -> dict:
    filters = state.get("search_filters", {})
    city = filters.get("city") or "Hồ Chí Minh"
    listing_type = filters.get("listing_type") or "sale"
    property_type = filters.get("property_type")

    rows = await district_price_overview(city=city, listing_type=listing_type, property_type=property_type)
    if not rows:
        content = f"Chưa đủ dữ liệu để phân tích {city} ({listing_type})."
    else:
        lines = [f"Phân tích giá theo quận tại {city} ({listing_type}):"]
        for row in rows[:10]:
            lines.append(
                f"- {row['district']}: {row['listings']} tin, "
                f"giá TB {row['avg_price']:.2f} tỷ, giá/m² TB {row['avg_price_per_m2']:.2f} triệu"
            )
        content = "\n".join(lines)

    return {
        "agent_results": {
            **state.get("agent_results", {}),
            "market_analysis": {
                "agent_name": "market_analysis",
                "content": content,
                "sources": [],
                "confidence": 0.7 if rows else 0.3,
            },
        },
    }
