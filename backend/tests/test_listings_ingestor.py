from data_pipeline.chunk import build_listing_chunks
from data_pipeline.ingestors.listings_ingestor import prepare_listing_chunks


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
    vectors = [[float(i) / 10] * 768 for i in range(len(chunks))]

    rows = prepare_listing_chunks(listing_id, chunks, vectors)

    assert len(rows) == len(chunks)
    assert rows[0]["parent_type"] == "listing"
    assert rows[0]["parent_id"] == 42
    assert rows[0]["chunk_type"] == chunks[0]["chunk_type"]
    assert rows[0]["embedding"] == vectors[0]
