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


def test_format_citations_omits_blank_optional_fields():
    chunks = [
        {
            "text": "Điều 5 nội dung.",
            "citation": {
                "doc_slug": "luat-dat-dai-2024",
                "chuong": "",
                "dieu_number": 5,
                "dieu_title": "",
                "khoan_number": None,
            },
        },
    ]

    text = format_citations(chunks)

    # No malformed dangling commas or empty parens for missing fields.
    assert ", , " not in text
    assert " - )" not in text
    assert "[1] (luat-dat-dai-2024, Điều 5)" in text


def test_format_citations_includes_khoan_when_present():
    chunks = [
        {
            "text": "Khoản 2 nội dung...",
            "citation": {
                "doc_slug": "luat-dat-dai-2024",
                "chuong": "Chương II",
                "dieu_number": 3,
                "dieu_title": "Quyền",
                "khoan_number": 2,
            },
        },
    ]

    text = format_citations(chunks)

    assert "Khoản 2" in text


def test_build_legal_prompt_warns_when_no_chunks():
    prompt = build_legal_prompt(query="Thủ tục sang tên?", chunks=[])

    assert "Thủ tục sang tên" in prompt
    assert "không tìm thấy" in prompt.lower() or "no relevant" in prompt.lower()
