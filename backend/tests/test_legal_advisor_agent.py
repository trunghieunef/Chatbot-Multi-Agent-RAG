import pytest

from chatbot.agents import legal_advisor


@pytest.mark.asyncio
async def test_legal_advisor_calls_hybrid_search_with_legal_filter(monkeypatch):
    captured = {}

    async def fake_hybrid(query, filters, parent_type):
        captured.update({"query": query, "filters": filters, "parent_type": parent_type})
        return [
            {
                "id": 1,
                "title": "Luật Đất đai 2024",
                "metadata_json": {"slug": "luat-dat-dai-2024"},
                "matched_chunk": {"chunk_type": "dieu", "text": "Điều 5..."},
                "citation": {
                    "doc_slug": "luat-dat-dai-2024",
                    "chuong": "Chương II",
                    "dieu_number": 5,
                    "dieu_title": "Quyền",
                },
            }
        ]

    async def fake_synth(query, chunks):
        return f"Tổng hợp dựa trên {len(chunks)} trích dẫn."

    monkeypatch.setattr(legal_advisor, "hybrid_search", fake_hybrid)
    monkeypatch.setattr(legal_advisor, "synthesize_legal_answer", fake_synth)

    state = {
        "user_query": "Quyền sử dụng đất gồm những gì?",
        "search_filters": {},
        "agent_results": {},
    }
    result = await legal_advisor.legal_advisor_node(state)

    assert captured["parent_type"] == "article"
    assert captured["filters"]["category"] == "legal"
    assert "1 trích dẫn" in result["agent_results"]["legal_advisor"]["content"]
