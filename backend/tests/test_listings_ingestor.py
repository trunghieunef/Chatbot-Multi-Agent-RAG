import csv

import pytest

from data_pipeline.chunk import build_listing_chunks
from data_pipeline.ingestors import listings_ingestor as li
from data_pipeline.ingestors.listings_ingestor import (
    listing_image_urls_from_row,
    prepare_listing_chunks,
    prepare_listing_image_rows,
    read_csv_rows,
)


class FailingEmbedder:
    async def embed_texts(self, texts):
        raise RuntimeError("embedding service unavailable")


class ExplodingEmbedder:
    async def embed_texts(self, texts):
        raise AssertionError("publish phase must complete before indexing")


class NoopGeocoder:
    async def geocode(self, address):
        return None


async def noop_ensure_vector_extension():
    return None


def sample_listing_row(product_id="publish-1"):
    return {
        "product_id": product_id,
        "title": "Can ho 2PN Quan 7",
        "description": "Can ho gan truong, phap ly ro",
        "price_text": "5 ty",
        "price_per_m2_text": "80 trieu/m2",
        "area_text": "62 m2",
        "bedrooms": "2",
        "bathrooms": "2",
        "address": "Quan 7, Ho Chi Minh",
        "url": f"https://example.test/listing/{product_id}",
    }


def test_prepare_listing_chunks_pairs_text_and_vectors():
    listing_id = 42
    listing_data = {
        "title": "Bán căn hộ 2PN Quận 7",
        "property_type": "Căn hộ chung cư",
        "listing_type": "sale",
        "price_text": "4,5 tỷ",
        "area_text": "75 m²",
        "district": "Quận 7",
        "city": "Hồ Chí Minh",
        "address": "Phường Tân Phong, Quận 7, Hồ Chí Minh",
        "description": "Gần trường học.",
    }
    chunks = build_listing_chunks(listing_data)
    vectors = [[float(i) / 10] * 1024 for i in range(len(chunks))]

    rows = prepare_listing_chunks(listing_id, chunks, vectors)

    assert len(rows) == len(chunks)
    assert rows[0]["parent_type"] == "listing"
    assert rows[0]["parent_id"] == 42
    assert rows[0]["chunk_type"] == chunks[0]["chunk_type"]
    assert rows[0]["embedding"] == vectors[0]


def test_read_csv_rows_strips_utf8_bom_from_header(tmp_path):
    path = tmp_path / "details.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["product_id", "title"])
        writer.writeheader()
        writer.writerow({"product_id": "p1", "title": "Listing"})

    rows = read_csv_rows(str(path))

    assert rows == [{"product_id": "p1", "title": "Listing"}]


def test_empty_ingest_result_shape():
    assert li.empty_ingest_result() == {
        "published": 0,
        "indexed": 0,
        "chunks": 0,
        "publish_errors": 0,
        "index_errors": 0,
    }


def test_listing_image_urls_from_row_accepts_json_and_dedupes():
    row = {
        "image_urls": (
            '["https://cdn.example.test/a.jpg", '
            '"https://cdn.example.test/b.webp", '
            '"https://cdn.example.test/a.jpg", '
            '"data:image/png;base64,abc"]'
        )
    }

    assert listing_image_urls_from_row(row) == [
        "https://cdn.example.test/a.jpg",
        "https://cdn.example.test/b.webp",
    ]


def test_prepare_listing_image_rows_marks_first_image_primary():
    listing = type("ListingStub", (), {"id": 7, "product_id": "p7"})()

    rows = prepare_listing_image_rows(
        listing,
        ["https://cdn.example.test/a.jpg", "https://cdn.example.test/b.jpg"],
    )

    assert rows == [
        {
            "listing_id": 7,
            "product_id": "p7",
            "image_url": "https://cdn.example.test/a.jpg",
            "sort_order": 0,
            "is_primary": True,
            "source": "batdongsan",
        },
        {
            "listing_id": 7,
            "product_id": "p7",
            "image_url": "https://cdn.example.test/b.jpg",
            "sort_order": 1,
            "is_primary": False,
            "source": "batdongsan",
        },
    ]


@pytest.mark.asyncio
async def test_publish_survives_embedding_failure(monkeypatch):
    async def fake_publish_batch(rows):
        assert rows[0]["product_id"] == "publish-1"
        return [type("PersistedListing", (), {"id": 101, "product_id": "publish-1"})()]

    monkeypatch.setattr(li, "publish_listing_batch", fake_publish_batch)
    monkeypatch.setattr(li, "build_geocoder", lambda **kwargs: NoopGeocoder())
    monkeypatch.setattr(li, "BGEEmbedder", lambda **kwargs: FailingEmbedder())
    monkeypatch.setattr(li, "ensure_vector_extension", noop_ensure_vector_extension)

    result = await li.ingest_listing_rows([sample_listing_row()], batch_size=1)

    assert result["published"] == 1
    assert result["indexed"] == 0
    assert result["chunks"] == 0
    assert result["publish_errors"] == 0
    assert result["index_errors"] == 1


@pytest.mark.asyncio
async def test_publish_phase_runs_before_embedder(monkeypatch):
    published = {"value": False}

    async def fake_publish_batch(rows):
        published["value"] = True
        return [type("PersistedListing", (), {"id": 102, "product_id": "publish-only-1"})()]

    monkeypatch.setattr(li, "publish_listing_batch", fake_publish_batch)
    monkeypatch.setattr(li, "build_geocoder", lambda **kwargs: NoopGeocoder())
    monkeypatch.setattr(li, "BGEEmbedder", lambda **kwargs: ExplodingEmbedder())
    monkeypatch.setattr(li, "ensure_vector_extension", noop_ensure_vector_extension)

    result = await li.ingest_listing_rows([sample_listing_row("publish-only-1")], batch_size=1)

    assert published["value"] is True
    assert result["published"] == 1
    assert result["indexed"] == 0
    assert result["chunks"] == 0
    assert result["index_errors"] == 1


@pytest.mark.asyncio
async def test_publish_survives_chunk_build_failure(monkeypatch):
    published = {"value": False}

    async def fake_publish_batch(rows):
        published["value"] = True
        return [type("PersistedListing", (), {"id": 103, "product_id": "chunk-fail-1"})()]

    def fail_chunk_build(_listing_data):
        raise RuntimeError("chunk builder unavailable")

    monkeypatch.setattr(li, "publish_listing_batch", fake_publish_batch)
    monkeypatch.setattr(li, "build_geocoder", lambda **kwargs: NoopGeocoder())
    monkeypatch.setattr(li, "build_listing_chunks", fail_chunk_build)
    monkeypatch.setattr(li, "BGEEmbedder", lambda **kwargs: FailingEmbedder())
    monkeypatch.setattr(li, "ensure_vector_extension", noop_ensure_vector_extension)

    result = await li.ingest_listing_rows([sample_listing_row("chunk-fail-1")], batch_size=1)

    assert published["value"] is True
    assert result["published"] == 1
    assert result["indexed"] == 0
    assert result["chunks"] == 0
    assert result["publish_errors"] == 0
    assert result["index_errors"] == 1
