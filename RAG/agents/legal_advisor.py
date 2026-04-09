"""
Legal Advisor Agent — Real estate legal consultation.

Uses RAG on a legal knowledge base covering:
- Luật Nhà ở 2023, Luật Kinh doanh BĐS 2023, Luật Đất đai 2024
- Thủ tục mua bán, công chứng, sang tên
- Thuế và phí chuyển nhượng
"""

from rag.state import ChatState


def legal_advisor_node(state: ChatState) -> dict:
    """
    Legal Advisor node: answer legal questions about real estate.

    TODO (Phase 3 full implementation):
    1. Search legal knowledge base in ChromaDB
    2. Retrieve relevant legal documents/articles
    3. Use Gemini to synthesize legal advice
    4. Include citations to specific laws/articles
    """
    query = state.get("user_query", "")

    response_text = (
        f"⚖️ **Tư vấn pháp lý bất động sản**\n\n"
        f"Câu hỏi: \"{query}\"\n\n"
        f"⏳ Module tư vấn pháp lý đang được phát triển.\n"
        f"Khi hoàn thành, tôi sẽ tư vấn dựa trên:\n"
        f"- Luật Nhà ở 2023\n"
        f"- Luật Kinh doanh Bất động sản 2023\n"
        f"- Luật Đất đai 2024\n"
        f"- Các nghị định, thông tư hướng dẫn liên quan\n\n"
        f"⚠️ Lưu ý: Thông tin pháp lý chỉ mang tính tham khảo. "
        f"Vui lòng liên hệ luật sư chuyên ngành để được tư vấn cụ thể."
    )

    return {
        "agent_results": {
            **state.get("agent_results", {}),
            "legal_advisor": {
                "agent_name": "legal_advisor",
                "content": response_text,
                "sources": [],
                "confidence": 0.6,
            },
        },
    }
