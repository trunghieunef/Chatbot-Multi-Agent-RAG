from data_pipeline.clean import (
    determine_listing_type,
    determine_property_type,
    extract_location,
    parse_area,
    parse_int_safe,
    parse_price_billion,
    parse_price_per_m2,
    row_to_listing,
)


def test_parse_vietnamese_price_units_to_billions():
    assert parse_price_billion("4,68 tỷ") == 4.68
    assert parse_price_billion("850 triệu") == 0.85
    assert parse_price_billion("120 nghìn") == 0.00012
    assert parse_price_billion("") is None


def test_parse_area_and_int_fields():
    assert parse_area("72,5 m²") == 72.5
    assert parse_area("không rõ") is None
    assert parse_int_safe("3 phòng ngủ") == 3
    assert parse_int_safe("") is None


def test_listing_type_and_property_type_rules():
    assert determine_listing_type({"title": "Cho thuê căn hộ", "url": "", "price_text": "15 triệu/tháng"}) == "rent"
    assert determine_listing_type({"title": "Bán nhà Quận 7", "url": "/nha-dat-ban", "price_text": "6 tỷ"}) == "sale"
    assert determine_property_type({"title": "Căn hộ chung cư 2PN", "property_type": ""}) == "Căn hộ chung cư"
    assert determine_property_type({"title": "Bán đất nền", "property_type": ""}) == "Đất nền"


def test_extract_location_from_address_tail():
    row = {"address": "Đường Nguyễn Văn Linh, Phường Tân Phong, Quận 7, Hồ Chí Minh"}
    assert extract_location(row) == ("Phường Tân Phong", "Quận 7", "Hồ Chí Minh")


def test_row_to_listing_maps_csv_fields():
    row = {
        "product_id": "123",
        "title": "Bán căn hộ 2PN Quận 7",
        "description": "Gần trường học, pháp lý rõ ràng",
        "price_text": "4,5 tỷ",
        "price_per_m2_text": "60 triệu/m²",
        "area_text": "75 m²",
        "bedrooms": "2 PN",
        "bathrooms": "2 WC",
        "address": "Phường Tân Phong, Quận 7, Hồ Chí Minh",
        "url": "https://batdongsan.com.vn/listing-123",
    }

    listing = row_to_listing(row)

    assert listing["product_id"] == "123"
    assert listing["listing_type"] == "sale"
    assert listing["property_type"] == "Căn hộ chung cư"
    assert listing["price"] == 4.5
    assert listing["area"] == 75
    assert listing["bedrooms"] == 2
    assert listing["district"] == "Quận 7"
