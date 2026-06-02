from crawler.core.listing_detail_parser import normalize_listing_detail
from crawler.rent.crawl_details import DETAIL_FIELDS as RENT_DETAIL_FIELDS
from crawler.sale.crawl_details import DETAIL_FIELDS as SALE_DETAIL_FIELDS


def test_normalize_listing_detail_marks_rent_when_price_per_month():
    raw = {
        "product_id": "p1",
        "title": "Cho thuê căn hộ 2PN",
        "price_text": "15 triệu/tháng",
        "area_text": "75 m²",
        "address": "Phường 1, Quận 7, Hồ Chí Minh",
        "url": "https://batdongsan.com.vn/cho-thue/abc",
    }

    detail = normalize_listing_detail(raw, source="rent")

    assert detail["listing_type"] == "rent"
    assert detail["price_unit"] == "million/month"


def test_normalize_listing_detail_marks_sale_for_sale_source():
    raw = {
        "product_id": "p2",
        "title": "Bán nhà phố",
        "price_text": "6,2 tỷ",
        "url": "https://batdongsan.com.vn/ban/xyz",
    }

    detail = normalize_listing_detail(raw, source="sale")

    assert detail["listing_type"] == "sale"
    assert detail["price_unit"] == "billion"


def test_crawler_detail_fields_include_normalized_keys():
    raw = {
        "product_id": "p3",
        "price_text": "5 ty",
        "listing_type": "",
    }

    detail = normalize_listing_detail(raw, source="sale")

    assert set(detail).issubset(SALE_DETAIL_FIELDS)
    assert set(detail).issubset(RENT_DETAIL_FIELDS)
