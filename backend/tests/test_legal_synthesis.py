import pytest

from chatbot.tools.legal_synthesis import build_legal_prompt, format_citations


def test_format_citations_renders_dieu_with_doc_slug():
    chunks = [
        {
            "text": "Điều 1...",
            "matched_chunk": {"chunk_type": "dieu"},
            "metadata_json": {"slug": "luat-dat-dai-2024"},
            "citation": {
                "doc_slug": "luat-dat-dai-2024",
                "chuong": "Chương I",
                "dieu_number": 1,
                "dieu_title": "Phạm vi",
            },
        },
    ]

    text = format_citations(chunks)

    assert "luat-dat-dai-2024" in text
    assert "Điều 1" in text
    assert "Chương I" in text


def test_build_legal_prompt_warns_when_no_chunks():
    prompt = build_legal_prompt(query="Thủ tục sang tên?", chunks=[])

    assert "Thủ tục sang tên" in prompt
    assert "không tìm thấy" in prompt.lower() or "no relevant" in prompt.lower()
