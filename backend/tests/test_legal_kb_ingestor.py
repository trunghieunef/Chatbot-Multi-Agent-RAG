from data_pipeline.ingestors.legal_kb_ingestor import build_article_payload, prepare_chunk_rows


def test_build_article_payload_uses_synthetic_url_and_legal_category():
    payload = build_article_payload(
        title="Luật Đất đai 2024",
        slug="luat-dat-dai-2024",
        body="Toàn văn luật...",
        source_filename="luat-dat-dai-2024.pdf",
        digest="a" * 64,
        chunks_count=12,
    )

    assert payload["title"] == "Luật Đất đai 2024"
    assert payload["category"] == "legal"
    assert payload["source"] == "luat-dat-dai-2024.pdf"
    assert payload["url"] == "legal://luat-dat-dai-2024"
    metadata = payload["metadata_json"]
    assert metadata["slug"] == "luat-dat-dai-2024"
    assert metadata["sha256"] == "a" * 64
    assert metadata["chunks_count"] == 12
    assert "ingested_at" in metadata


def test_prepare_chunk_rows_pairs_chunks_and_vectors():
    chunks = [
        {"chunk_type": "dieu", "text": "Điều 1. ...", "citation": {"doc_slug": "x", "chuong": "Chương I", "dieu_number": 1, "dieu_title": "Phạm vi"}},
        {"chunk_type": "dieu", "text": "Điều 2. ...", "citation": {"doc_slug": "x", "chuong": "Chương I", "dieu_number": 2, "dieu_title": "Đối tượng"}},
    ]
    vectors = [[0.1] * 1024, [0.2] * 1024]

    rows = prepare_chunk_rows(article_id=42, chunks=chunks, vectors=vectors)

    assert rows[0]["parent_type"] == "article"
    assert rows[0]["parent_id"] == 42
    assert rows[0]["chunk_type"] == "dieu"
    assert rows[0]["text"].startswith("Điều 1")
    assert rows[0]["embedding"] == [0.1] * 1024


def test_prepare_chunk_rows_persists_citation_in_metadata_json():
    chunks = [
        {
            "chunk_type": "khoan",
            "text": "Điều 3 Khoản 2...",
            "citation": {
                "doc_slug": "luat-dat-dai-2024",
                "chuong": "Chương II",
                "dieu_number": 3,
                "dieu_title": "Quyền",
                "khoan_number": 2,
            },
        },
    ]
    vectors = [[0.0] * 1024]

    rows = prepare_chunk_rows(article_id=7, chunks=chunks, vectors=vectors)

    assert rows[0]["metadata_json"] == {
        "citation": {
            "doc_slug": "luat-dat-dai-2024",
            "chuong": "Chương II",
            "dieu_number": 3,
            "dieu_title": "Quyền",
            "khoan_number": 2,
        }
    }


def test_prepare_chunk_rows_omits_metadata_json_when_no_citation():
    chunks = [{"chunk_type": "dieu", "text": "X"}]
    vectors = [[0.0] * 1024]

    rows = prepare_chunk_rows(article_id=1, chunks=chunks, vectors=vectors)

    assert "metadata_json" not in rows[0]
