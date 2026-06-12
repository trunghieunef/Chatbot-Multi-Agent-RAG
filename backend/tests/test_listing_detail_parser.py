from crawler.core.listing_detail_parser import normalize_listing_detail
from crawler.core.listing_images import image_urls_json_from_page
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
    assert "image_urls" in SALE_DETAIL_FIELDS
    assert "image_urls" in RENT_DETAIL_FIELDS


class FakeImage:
    def __init__(self, attrs):
        self.attrs = attrs

    def get_attribute(self, name):
        return self.attrs.get(name)


class FakePage:
    def __init__(self, images):
        self.images = images

    def query_selector_all(self, selector):
        assert selector == "img"
        return self.images


def test_image_urls_json_from_page_normalizes_and_dedupes_urls():
    page = FakePage(
        [
            FakeImage({"src": "https://staticfile.batdongsan.com.vn/images/app/app-store.png"}),
            FakeImage({"src": "https://file4.batdongsan.com.vn/resize/1275x717/2026/06/10/listing-a_wm.jpg"}),
            FakeImage({"data-src": "https://file4.batdongsan.com.vn/resize/1275x717/2026/06/10/listing-b_wm.webp"}),
            FakeImage({"src": "data:image/png;base64,abc"}),
            FakeImage({"src": "https://file4.batdongsan.com.vn/resize/200x200/2026/06/10/listing-a_wm.jpg"}),
            FakeImage({"src": "https://file4.batdongsan.com.vn/resize/1275x717/2026/06/10/listing-a_wm.jpg"}),
        ]
    )

    image_urls = image_urls_json_from_page(page, "https://example.test/detail/1")

    assert image_urls == (
        '["https://file4.batdongsan.com.vn/resize/1275x717/2026/06/10/listing-a_wm.jpg", '
        '"https://file4.batdongsan.com.vn/resize/1275x717/2026/06/10/listing-b_wm.webp"]'
    )
