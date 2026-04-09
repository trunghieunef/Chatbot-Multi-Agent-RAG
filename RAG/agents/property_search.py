"""
Property Search Agent — Find real estate listings matching user needs.

Uses vector search (ChromaDB) + SQL filters (PostgreSQL) to find
relevant listings, then uses Gemini to generate a natural language summary.
"""

import google.generativeai as genai

from rag.config import GEMINI_API_KEY, GEMINI_MODEL
from rag.state import ChatState

PROPERTY_PROMPT = """Bạn là chuyên viên tư vấn bất động sản.

Dựa trên kết quả tìm kiếm dưới đây, hãy tư vấn cho khách hàng:

**Câu hỏi**: {query}

**Bộ lọc áp dụng**: {filters}

**Kết quả tìm kiếm** ({count} bất động sản):
{listings_text}

Hãy:
1. Tóm tắt kết quả tìm kiếm một cách tự nhiên
2. Highlight 3-5 lựa chọn nổi bật nhất
3. So sánh nhanh giá/diện tích giữa các lựa chọn
4. Đưa ra nhận xét và gợi ý

Trả lời bằng tiếng Việt, thân thiện và chuyên nghiệp.
"""


def property_search_node(state: ChatState) -> dict:
    """
    Property Search node: find listings matching the query.

    TODO (Phase 3 full implementation):
    1. Query ChromaDB with embedded query for semantic search
    2. Query PostgreSQL with extracted filters
    3. Combine and rank results
    4. Use Gemini to generate natural language response
    """
    query = state.get("user_query", "")
    filters = state.get("search_filters", {})

    # ─── Placeholder: Will be replaced with real vector + SQL search ───
    # In Phase 3, this will:
    # - Call ChromaDB for semantic similarity search
    # - Call PostgreSQL for filtered structured search
    # - Merge and deduplicate results
    # - Pass to Gemini for response generation

    response_text = (
        f"🏠 **Kết quả tìm kiếm bất động sản**\n\n"
        f"Tôi đang tìm kiếm theo yêu cầu: \"{query}\"\n"
        f"Bộ lọc: {filters if filters else 'Không có bộ lọc cụ thể'}\n\n"
        f"⏳ Hệ thống RAG đang được phát triển. "
        f"Khi hoàn thành, tôi sẽ tìm kiếm trong cơ sở dữ liệu hàng nghìn tin đăng "
        f"và đưa ra gợi ý phù hợp nhất cho bạn."
    )

    return {
        "agent_results": {
            **state.get("agent_results", {}),
            "property_search": {
                "agent_name": "property_search",
                "content": response_text,
                "sources": [],
                "confidence": 0.8,
            },
        },
    }
