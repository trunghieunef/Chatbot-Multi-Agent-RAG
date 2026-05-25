from data_pipeline.chunk import build_listing_chunks


def test_build_listing_chunks_uses_precomputed_intent_tags():
    listing = {
        "title": "Bán căn hộ 2PN",
        "property_type": "Căn hộ chung cư",
        "listing_type": "sale",
        "price_text": "4 tỷ",
        "area_text": "75 m²",
        "district": "Quận 7",
        "city": "Hồ Chí Minh",
        "address": "Phường 1, Quận 7",
        "description": "Mô tả ngắn.",
        "intent_tags": ["view sông", "gần trường mới"],
    }

    chunks = build_listing_chunks(listing)
    by_type = {chunk["chunk_type"]: chunk for chunk in chunks}

    assert by_type["intent_tags"]["text"] == "Nhu cầu phù hợp: view sông, gần trường mới"


def test_build_listing_chunks_falls_back_to_rule_based_tags_when_missing():
    listing = {
        "title": "Bán căn hộ 2PN",
        "property_type": "Căn hộ chung cư",
        "listing_type": "sale",
        "price_text": "4 tỷ",
        "district": "Quận 7",
        "city": "Hồ Chí Minh",
        "description": "Gần trường học, sổ hồng đầy đủ.",
    }

    chunks = build_listing_chunks(listing)
    by_type = {chunk["chunk_type"]: chunk for chunk in chunks}

    assert "gần trường" in by_type["intent_tags"]["text"]
    assert "pháp lý rõ" in by_type["intent_tags"]["text"]
