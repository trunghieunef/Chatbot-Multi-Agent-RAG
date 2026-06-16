from data_pipeline.clean import (
    determine_listing_type,
    determine_property_type,
    extract_location,
    parse_area,
    parse_int_safe,
    parse_price_billion,
    parse_price_per_m2,
    row_to_article,
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


def test_row_to_listing_keeps_non_admin_address_parts_out_of_location():
    row = {
        "product_id": "45915053",
        "title": "Bán shophouse tại The Miami",
        "price_text": "22,8 tỷ",
        "area_text": "90,8 m²",
        "address": "GS05-05, The Miami, Phường Tây Mỗ, Hà Nội",
    }

    listing = row_to_listing(row)

    assert listing["address"] == "GS05-05, The Miami"
    assert listing["ward"] == "Phường Tây Mỗ"
    assert listing["district"] is None
    assert listing["city"] == "Hà Nội"


def test_row_to_listing_keeps_street_and_project_in_address():
    row = {
        "product_id": "45893185",
        "title": "Cho thuê căn hộ Bcons City",
        "price_text": "6 triệu/tháng",
        "area_text": "55 m²",
        "address": "57, Bcons City, Đường Thống Nhất, Phường Đông Hòa, Thành phố Dĩ An, Bình Dương",
        "url": "/nha-dat-cho-thue/abc",
    }

    listing = row_to_listing(row)

    assert listing["address"] == "57, Bcons City, Đường Thống Nhất"
    assert listing["ward"] == "Phường Đông Hòa"
    assert listing["district"] == "Thành phố Dĩ An"
    assert listing["city"] == "Bình Dương"


def test_extract_location_from_breadcrumb_address():
    row = {
        "address": "Cho thuê, Hồ Chí Minh, Bình Thạnh, Căn hộ chung cư tại Vinhomes Central Park",
    }

    assert extract_location(row) == ("", "Bình Thạnh", "Hồ Chí Minh")


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


def test_row_to_listing_uses_breadcrumb_location_and_property_type():
    row = {
        "product_id": "45887621",
        "title": "Cập nhật giỏ hàng giá tốt nhất Vinhomes Central Park",
        "price_text": "17 triệu/tháng",
        "area_text": "54 m²",
        "address": "Cho thuê, Hồ Chí Minh, Bình Thạnh, Căn hộ chung cư tại Vinhomes Central Park",
        "url": "https://batdongsan.com.vn/cho-thue-can-ho-chung-cu-vinhomes-central-park-pr45887621",
    }

    listing = row_to_listing(row)

    assert listing["listing_type"] == "rent"
    assert listing["property_type"] == "Căn hộ chung cư"
    assert listing["district"] == "Bình Thạnh"
    assert listing["city"] == "Hồ Chí Minh"


def test_row_to_listing_classifies_shophouse_from_breadcrumb_before_nha_pho():
    row = {
        "product_id": "45913352",
        "title": "Quỹ Shophouse 5 tầng cho thuê lõi 58 tòa cc",
        "price_text": "100 triệu/tháng",
        "area_text": "150 m²",
        "address": "Cho thuê, Hà Nội, Nam Từ Liêm, Shophouse, nhà phố thương mại tại Vinhomes Smart City",
        "url": "https://batdongsan.com.vn/cho-thue-shophouse-nha-pho-thuong-mai-pr45913352",
    }

    listing = row_to_listing(row)

    assert listing["property_type"] == "Shophouse"
    assert listing["district"] == "Nam Từ Liêm"
    assert listing["city"] == "Hà Nội"


def test_row_to_listing_rent_price_unit_is_million_per_month():
    row = {
        "product_id": "456",
        "title": "Cho thuê căn hộ Quận 7",
        "url": "/nha-dat-cho-thue/abc",
        "price_text": "15 triệu/tháng",
        "area_text": "60 m²",
        "address": "Phường Tân Phong, Quận 7, Hồ Chí Minh",
    }
    listing = row_to_listing(row)
    assert listing["listing_type"] == "rent"
    assert listing["price_unit"] == "million/month"


def test_row_to_listing_rent_without_thang_falls_back_to_billion():
    row = {
        "product_id": "789",
        "title": "Cho thuê",
        "url": "/nha-dat-cho-thue/xyz",
        "price_text": "15 triệu",
        "area_text": "60 m²",
        "address": "Phường 1, Quận 7, Hồ Chí Minh",
    }
    listing = row_to_listing(row)
    assert listing["listing_type"] == "rent"
    assert listing["price_unit"] == "billion"


def test_parse_price_per_m2():
    assert parse_price_per_m2("60 triệu/m²") == 60.0
    assert parse_price_per_m2("") is None


def test_row_to_article_parses_vietnamese_datetime_as_date():
    article = row_to_article(
        {
            "title": "Tin thị trường",
            "body": "Nội dung",
            "category": "news",
            "source": "batdongsan.com",
            "post_date": "15/6/2026 17:00",
            "url": "https://example.test/news",
        }
    )

    assert article["post_date"].isoformat() == "2026-06-15"
