"""Contract test: confirms the legal flow renders citations using the SAME
shape that ``chatbot.tools.hybrid_search.resolve_to_article_records`` actually
emits (article row + ``matched_chunk`` + top-level ``citation`` lifted from
``chunks.metadata_json``).

Without this test, ``test_legal_advisor_agent.py`` could pass forever even
when production drops citations between ingestion and retrieval.
"""

from chatbot.tools.legal_synthesis import format_citations


def _resolved_article_record(citation: dict) -> dict:
    """Mirror the shape produced by resolve_to_article_records.

    See chatbot/tools/hybrid_search.py:resolve_to_article_records:
    selects (id, title, category, source, post_date, url, metadata_json) and
    attaches matched_chunk + citation (when chunks.metadata_json carries one).
    """
    return {
        "id": 1,
        "title": "Luật Đất đai 2024",
        "category": "legal",
        "source": "luat-dat-dai-2024.pdf",
        "post_date": None,
        "url": "legal://luat-dat-dai-2024",
        "metadata_json": {
            "slug": "luat-dat-dai-2024",
            "sha256": "a" * 64,
            "chunks_count": 5,
            "ingested_at": "2026-07-01T00:00:00Z",
        },
        "matched_chunk": {
            "chunk_type": "khoan",
            "text": "Điều 3 Khoản 2 nội dung...",
            "distance": 0.21,
            "rerank_score": 0.93,
        },
        "text": "Điều 3 Khoản 2 nội dung...",
        "citation": citation,
    }


def test_format_citations_against_resolved_article_shape():
    record = _resolved_article_record(
        {
            "doc_slug": "luat-dat-dai-2024",
            "chuong": "Chương II",
            "dieu_number": 3,
            "dieu_title": "Quyền",
            "khoan_number": 2,
        }
    )

    text = format_citations([record])

    assert "luat-dat-dai-2024" in text
    assert "Chương II" in text
    assert "Điều 3" in text
    assert "Khoản 2" in text


def test_format_citations_handles_resolved_record_without_citation():
    """If the per-chunk metadata_json wasn't persisted (or hybrid_search didn't
    surface it), format_citations must not crash and must surface a useful slug
    derived from the article-level metadata_json."""
    record = _resolved_article_record({})
    record.pop("citation")

    text = format_citations([record])

    assert "luat-dat-dai-2024" in text
    assert "[1]" in text
