"""
Router Agent — Intent classification and agent routing.

Analyzes the user query to determine:
1. What is the user's intent?
2. Which specialized agent(s) should handle this?
3. What search filters can be extracted?

Uses Google Gemini for classification.
"""

import json
import google.generativeai as genai

from rag.config import GEMINI_API_KEY, GEMINI_MODEL
from rag.state import ChatState

ROUTER_PROMPT = """Bạn là Router Agent trong hệ thống tư vấn bất động sản.

Nhiệm vụ: Phân tích câu hỏi của người dùng và xác định:
1. **intent**: Ý định chính (property_search, market_analysis, legal_advice, investment_advice, general)
2. **target_agents**: Danh sách agent cần xử lý (có thể nhiều agent)
3. **search_filters**: Các bộ lọc tìm kiếm trích xuất được (nếu có)

Các agent có sẵn:
- **property_search**: Tìm kiếm bất động sản theo yêu cầu (giá, diện tích, khu vực, loại hình)
- **market_analysis**: Phân tích thị trường, xu hướng giá, thống kê
- **legal_advisor**: Tư vấn pháp lý (thủ tục, luật, thuế, hợp đồng)
- **investment_advisor**: Tư vấn đầu tư, ROI, so sánh kênh đầu tư

Trích xuất search_filters nếu có:
- city: Tỉnh/Thành phố
- district: Quận/Huyện
- property_type: Loại BĐS (apartment, house, land, shophouse)
- min_price, max_price: Khoảng giá (tỷ VND)
- min_area, max_area: Khoảng diện tích (m²)
- bedrooms: Số phòng ngủ
- listing_type: sale hoặc rent

Trả về JSON:
```json
{
    "intent": "property_search",
    "target_agents": ["property_search"],
    "search_filters": {
        "city": "Hồ Chí Minh",
        "district": "Quận 7",
        "property_type": "apartment",
        "max_price": 5,
        "bedrooms": 2
    }
}
```

Câu hỏi người dùng: {query}
"""


def router_node(state: ChatState) -> dict:
    """
    Router node: classify intent and route to appropriate agents.
    """
    query = state.get("user_query", "")

    if not GEMINI_API_KEY:
        # Fallback: simple keyword-based routing
        return _keyword_router(query)

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)

        response = model.generate_content(
            ROUTER_PROMPT.format(query=query),
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        result = json.loads(response.text)
        return {
            "intent": result.get("intent", "general"),
            "target_agents": result.get("target_agents", ["property_search"]),
            "search_filters": result.get("search_filters", {}),
        }

    except Exception as e:
        print(f"[Router] Error: {e}")
        return _keyword_router(query)


def _keyword_router(query: str) -> dict:
    """Fallback keyword-based routing when Gemini is unavailable."""
    q = query.lower()

    if any(w in q for w in ["tìm", "mua", "thuê", "căn hộ", "nhà", "đất", "phòng"]):
        return {
            "intent": "property_search",
            "target_agents": ["property_search"],
            "search_filters": {},
        }
    elif any(w in q for w in ["giá", "thị trường", "xu hướng", "biến động", "thống kê"]):
        return {
            "intent": "market_analysis",
            "target_agents": ["market_analysis"],
            "search_filters": {},
        }
    elif any(w in q for w in ["pháp lý", "luật", "thủ tục", "công chứng", "thuế", "hợp đồng", "sổ đỏ"]):
        return {
            "intent": "legal_advice",
            "target_agents": ["legal_advisor"],
            "search_filters": {},
        }
    elif any(w in q for w in ["đầu tư", "roi", "lợi nhuận", "sinh lời", "kênh"]):
        return {
            "intent": "investment_advice",
            "target_agents": ["investment_advisor"],
            "search_filters": {},
        }
    else:
        return {
            "intent": "property_search",
            "target_agents": ["property_search"],
            "search_filters": {},
        }
