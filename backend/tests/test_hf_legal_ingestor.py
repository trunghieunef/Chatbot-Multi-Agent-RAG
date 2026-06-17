from data_pipeline.ingestors.hf_legal_ingestor import (
    build_hf_legal_article_payload,
    extract_dataset_server_rows,
    ingest_hf_legal_documents,
    is_real_estate_legal_document,
    normalize_hf_legal_body,
)
import pytest


def test_is_real_estate_legal_document_matches_real_estate_metadata():
    row = {
        "id": "doc-1",
        "title": "Luật Đất đai 2024",
        "description": "Quy định về quyền sử dụng đất và giấy chứng nhận",
    }

    assert is_real_estate_legal_document(row) is True


def test_is_real_estate_legal_document_matches_vietnamese_d_char():
    row = {"id": "doc-1", "title": "Luật Đất đai 2024"}

    assert is_real_estate_legal_document(row) is True


def test_is_real_estate_legal_document_rejects_unrelated_metadata():
    row = {
        "id": "doc-2",
        "title": "Quy định về an toàn thực phẩm",
        "description": "Điều kiện sản xuất thực phẩm",
    }

    assert is_real_estate_legal_document(row) is False


def test_normalize_hf_legal_body_strips_html():
    row = {
        "content_html": (
            "<table><tr><td><p><b>Điều 1. Phạm vi điều chỉnh</b></p>"
            "<p>Luật này quy định về đất đai.</p></td></tr></table>"
        )
    }

    body = normalize_hf_legal_body(row)

    assert "Điều 1. Phạm vi điều chỉnh" in body
    assert "Luật này quy định về đất đai." in body
    assert "<table" not in body


def test_extract_dataset_server_rows_unwraps_row_payloads():
    payload = {
        "rows": [
            {"row": {"id": "4260", "content_html": "<p>Luật Đất đai</p>"}},
            {"row": {"id": "4261", "content_html": "<p>Luật Nhà ở</p>"}},
        ]
    }

    rows = extract_dataset_server_rows(payload)

    assert rows == [
        {"id": "4260", "content_html": "<p>Luật Đất đai</p>"},
        {"id": "4261", "content_html": "<p>Luật Nhà ở</p>"},
    ]


def test_build_hf_legal_article_payload_uses_stable_hf_url_and_metadata():
    payload = build_hf_legal_article_payload(
        doc_id="4260",
        title="Luật Đất đai 2024",
        body="Điều 1. Phạm vi",
        chunks_count=3,
    )

    assert payload["category"] == "legal"
    assert payload["source"] == "huggingface:th1nhng0/vietnamese-legal-documents"
    assert payload["url"] == "legal-hf://4260"
    assert payload["metadata_json"]["hf_dataset"] == "th1nhng0/vietnamese-legal-documents"
    assert payload["metadata_json"]["hf_doc_id"] == "4260"
    assert payload["metadata_json"]["chunks_count"] == 3


@pytest.mark.asyncio
async def test_ingest_hf_legal_documents_does_not_load_embedder_without_matches(monkeypatch):
    from data_pipeline.ingestors import hf_legal_ingestor as ingestor

    async def fake_ensure_schema():
        return None

    class ExplodingEmbedder:
        def __init__(self, *args, **kwargs):
            raise AssertionError("embedder should be lazy")

    monkeypatch.setattr(ingestor, "_ensure_schema", fake_ensure_schema)
    monkeypatch.setattr(ingestor, "BGEEmbedder", ExplodingEmbedder)

    result = await ingest_hf_legal_documents(
        limit=1,
        scan_limit=1,
        dataset_rows=[
            {
                "id": "doc-food",
                "content_html": "<p>Quy định về an toàn thực phẩm.</p>",
            }
        ],
    )

    assert result == {"scanned": 1, "matched": 0, "documents": 0, "chunks": 0}


@pytest.mark.asyncio
async def test_ingest_hf_legal_documents_dry_run_does_not_load_embedder_for_matches(monkeypatch):
    from data_pipeline.ingestors import hf_legal_ingestor as ingestor

    async def fake_ensure_schema():
        raise AssertionError("dry-run should not touch schema")

    class ExplodingEmbedder:
        def __init__(self, *args, **kwargs):
            raise AssertionError("dry-run should not load embedder")

    monkeypatch.setattr(ingestor, "_ensure_schema", fake_ensure_schema)
    monkeypatch.setattr(ingestor, "BGEEmbedder", ExplodingEmbedder)

    result = await ingest_hf_legal_documents(
        limit=1,
        scan_limit=1,
        dry_run=True,
        dataset_rows=[
            {
                "id": "doc-land",
                "content_html": "<p>Điều 1. Luật này quy định về đất đai.</p>",
            }
        ],
    )

    assert result == {"scanned": 1, "matched": 1, "documents": 0, "chunks": 1}
