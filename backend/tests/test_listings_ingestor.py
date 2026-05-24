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
    vectors = [[0.1] * 768, [0.2] * 768, [0.3] * 768, [0.4] * 768]

    rows = prepare_listing_chunks(listing_id, listing_data, vectors)

    assert rows[0]["parent_type"] == "listing"
    assert rows[0]["parent_id"] == 42
    assert rows[0]["chunk_type"] == "overview"
    assert rows[0]["embedding"] == [0.1] * 768
