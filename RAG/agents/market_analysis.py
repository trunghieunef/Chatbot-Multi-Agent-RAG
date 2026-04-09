"""
Market Analysis Agent — Analyze real estate market trends and statistics.

Queries PostgreSQL aggregations for price trends, supply/demand,
and regional comparisons.
"""

from rag.state import ChatState


def market_analysis_node(state: ChatState) -> dict:
    """
    Market Analysis node: provide market insights and trends.

    TODO (Phase 3 full implementation):
    1. Query PostgreSQL for aggregate statistics
    2. Calculate price trends over time
    3. Compare regions/districts
    4. Use Gemini to generate analytical report
    """
    query = state.get("user_query", "")

    response_text = (
        f"📊 **Phân tích thị trường bất động sản**\n\n"
        f"Câu hỏi: \"{query}\"\n\n"
        f"⏳ Module phân tích thị trường đang được phát triển.\n"
        f"Khi hoàn thành, tôi sẽ cung cấp:\n"
        f"- Xu hướng giá theo khu vực và thời gian\n"
        f"- So sánh giá giữa các quận/huyện\n"
        f"- Thống kê cung-cầu theo loại hình BĐS\n"
        f"- Phân tích giá/m² trung bình\n"
        f"- Dự báo xu hướng ngắn hạn"
    )

    return {
        "agent_results": {
            **state.get("agent_results", {}),
            "market_analysis": {
                "agent_name": "market_analysis",
                "content": response_text,
                "sources": [],
                "confidence": 0.7,
            },
        },
    }
