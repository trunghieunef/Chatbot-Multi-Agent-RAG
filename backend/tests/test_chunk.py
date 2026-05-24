from data_pipeline.chunk import build_listing_chunks


def test_build_listing_chunks_creates_expected_chunk_types():
    listing = {
        "title": "Bán căn hộ 2PN Quận 7",
        "property_type": "Căn hộ chung cư",
        "listing_type": "sale",
        "price_text": "4,5 tỷ",
        "area_text": "75 m²",
        "bedrooms": 2,
        "bathrooms": 2,
        "district": "Quận 7",
        "city": "Hồ Chí Minh",
        "address": "Phường Tân Phong, Quận 7, Hồ Chí Minh",
        "description": "Căn hộ gần trường học, gần siêu thị, an ninh tốt.",
        "legal_status": "Sổ hồng",
        "furniture": "Đầy đủ",
    }

    chunks = build_listing_chunks(listing)
    by_type = {chunk["chunk_type"]: chunk for chunk in chunks}

    assert set(by_type) == {"overview", "description", "location", "intent_tags"}
    assert "Bán căn hộ 2PN Quận 7" in by_type["overview"]["text"]
    assert "Quận 7" in by_type["location"]["text"]
    assert "gần trường" in by_type["intent_tags"]["text"]


def test_build_listing_chunks_skips_empty_description_chunk():
    listing = {
        "title": "Bán đất nền",
        "property_type": "Đất nền",
        "listing_type": "sale",
        "price_text": "",
        "area_text": "",
        "district": "",
        "city": "",
        "address": "",
        "description": "",
    }

    chunks = build_listing_chunks(listing)

    assert [chunk["chunk_type"] for chunk in chunks] == ["overview"]


def test_build_listing_chunks_no_intent_when_keywords_absent():
    listing = {
        "title": "Bán căn hộ",
        "property_type": "Căn hộ chung cư",
        "listing_type": "sale",
        "price_text": "4 tỷ",
        "description": "Căn hộ rộng rãi, thoáng mát.",
        "address": "",
        "district": "Quận 7",
        "city": "Hồ Chí Minh",
    }

    chunks = build_listing_chunks(listing)
    chunk_types = [chunk["chunk_type"] for chunk in chunks]

    assert "intent_tags" not in chunk_types


def test_build_listing_chunks_location_skips_missing_district():
    listing = {
        "title": "Bán nhà",
        "property_type": "Nhà riêng",
        "listing_type": "sale",
        "price_text": "5 tỷ",
        "district": "",
        "city": "Hồ Chí Minh",
        "address": "",
        "description": "",
    }

    chunks = build_listing_chunks(listing)
    overview = next(chunk for chunk in chunks if chunk["chunk_type"] == "overview")

    assert "Khu vực: Hồ Chí Minh" in overview["text"]
    assert ", Hồ Chí Minh" not in overview["text"].replace("Khu vực: ", "")
