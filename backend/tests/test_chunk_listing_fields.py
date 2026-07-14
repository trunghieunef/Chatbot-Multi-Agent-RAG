from data_pipeline.chunk import build_listing_chunks


def test_overview_includes_frontage_and_direction():
    listing = {
        "title": "Nhà đẹp",
        "property_type": "Nhà riêng",
        "price_text": "5 tỷ",
        "area_text": "50 m²",
        "district": "Quận 1",
        "city": "TP.HCM",
        "frontage": "5m",
        "road_width": "8m",
        "direction": "Đông Nam",
        "floors": "3",
    }
    chunks = build_listing_chunks(listing)
    overview = next(c["text"] for c in chunks if c["chunk_type"] == "overview")
    assert "Mặt tiền: 5m" in overview
    assert "Đường vào: 8m" in overview
    assert "Hướng: Đông Nam" in overview
    assert "Số tầng: 3" in overview


def test_overview_omits_empty_fields():
    listing = {"title": "Nhà", "price_text": "2 tỷ"}  # no frontage/direction
    chunks = build_listing_chunks(listing)
    overview = next(c["text"] for c in chunks if c["chunk_type"] == "overview")
    assert "Mặt tiền" not in overview
    assert "Hướng" not in overview
