"""
Investment Advisor Agent — Real estate investment analysis.

Provides ROI calculations, investment comparisons,
risk analysis, and rental yield estimates.
"""

from chatbot.state import ChatState


def investment_advisor_node(state: ChatState) -> dict:
    """
    Investment Advisor node: analyze investment opportunities.

    TODO (Phase 3 full implementation):
    1. Retrieve relevant listings and market data
    2. Calculate ROI, rental yield, price appreciation
    3. Compare investment options
    4. Use Gemini to generate investment advice
    """
    query = state.get("user_query", "")

    response_text = (
        f"💰 **Tư vấn đầu tư bất động sản**\n\n"
        f"Câu hỏi: \"{query}\"\n\n"
        f"⏳ Module tư vấn đầu tư đang được phát triển.\n"
        f"Khi hoàn thành, tôi sẽ phân tích:\n"
        f"- ROI (tỷ suất lợi nhuận) dự kiến\n"
        f"- Lợi suất cho thuê (rental yield)\n"
        f"- Tiềm năng tăng giá theo khu vực\n"
        f"- So sánh các kênh đầu tư (BĐS vs vàng vs chứng khoán)\n"
        f"- Đánh giá rủi ro và khuyến nghị\n\n"
        f"⚠️ Lưu ý: Phân tích đầu tư chỉ mang tính tham khảo, "
        f"không phải lời khuyên tài chính chính thức."
    )

    return {
        "agent_results": {
            **state.get("agent_results", {}),
            "investment_advisor": {
                "agent_name": "investment_advisor",
                "content": response_text,
                "sources": [],
                "confidence": 0.6,
            },
        },
    }
