"""Property Search Agent — Find real estate listings matching user needs.

Calls hybrid_search (PostgreSQL SQL filter + pgvector kNN + Cohere rerank)
to retrieve listings, then formats them for the synthesizer.
"""

from chatbot.state import ChatState
from chatbot.tools.hybrid_search import hybrid_search

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


def format_listing_results(listings: list[dict]) -> str:
    if not listings:
        return "Không tìm thấy bất động sản phù hợp trong dữ liệu hiện có."

    lines = []
    for index, item in enumerate(listings, start=1):
        lines.append(
            f"{index}. {item.get('title') or 'Không có tiêu đề'} | "
            f"{item.get('price_text') or item.get('price') or 'Chưa rõ giá'} | "
            f"{item.get('area_text') or item.get('area') or 'Chưa rõ diện tích'} | "
            f"{item.get('district') or ''}, {item.get('city') or ''} | "
            f"{item.get('url') or ''}"
        )
    return "\n".join(lines)


async def property_search_node(state: ChatState) -> dict:
    query = state.get("user_query", "")
    filters = state.get("search_filters", {})
    listings = await hybrid_search(query=query, filters=filters, parent_type="listing")
    listings_text = format_listing_results(listings)
    response_text = PROPERTY_PROMPT.format(
        query=query,
        filters=filters if filters else "Không có bộ lọc cụ thể",
        count=len(listings),
        listings_text=listings_text,
    )

    return {
        "agent_results": {
            **state.get("agent_results", {}),
            "property_search": {
                "agent_name": "property_search",
                "content": response_text,
                "sources": [item.get("url") for item in listings if item.get("url")],
                "confidence": 0.85 if listings else 0.35,
            },
        },
    }
