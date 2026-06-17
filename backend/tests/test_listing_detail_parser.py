from crawler.core.listing_detail_parser import (
    extract_listing_address_from_page,
    extract_listing_property_type_from_page,
    is_shell_listing_page,
    normalize_listing_detail,
)
from crawler.core.listing_images import image_urls_json_from_page
from crawler.rent import crawl_details as rent_crawl_details
from crawler.rent.crawl_details import DETAIL_FIELDS as RENT_DETAIL_FIELDS
from crawler.sale import crawl_details as sale_crawl_details
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


def test_shell_listing_page_detection_rejects_challenge_titles():
    assert is_shell_listing_page("batdongsan.com.vn", "Just a moment...")
    assert is_shell_listing_page("batdongsan.com.vn", "batdongsan.com.vn")
    assert is_shell_listing_page("", "Access Denied")
    assert not is_shell_listing_page(
        "Cho thuê căn hộ Vinhomes Central Park",
        "Cho thuê căn hộ Vinhomes Central Park",
    )


class FakeElement:
    def __init__(self, text="", children=None):
        self.text = text
        self.children = children or {}

    def inner_text(self):
        return self.text

    def query_selector_all(self, selector):
        return self.children.get(selector, [])


class FakeAddressPage:
    def __init__(self, elements):
        self.elements = elements

    def query_selector(self, selector):
        return self.elements.get(selector)


def test_extract_listing_address_prefers_ldp_address_line_1_over_breadcrumb():
    page = FakeAddressPage(
        {
            ".re__ldp-address .re__address-line-1": FakeElement(
                "Khu đô thị Nam Thăng Long - Ciputra, Phường Phú Thượng, Quận Tây Hồ, Hà Nội"
            ),
            ".re__breadcrumb": FakeElement(
                children={
                    "a": [
                        FakeElement("Bán"),
                        FakeElement("Hà Nội"),
                        FakeElement("Tây Hồ"),
                        FakeElement("Nhà biệt thự, liền kề tại Khu đô thị Nam Thăng Long - Ciputra"),
                    ]
                }
            ),
        }
    )

    address = extract_listing_address_from_page(page)

    assert (
        address
        == "Khu đô thị Nam Thăng Long - Ciputra, Phường Phú Thượng, Quận Tây Hồ, Hà Nội"
    )


def test_extract_listing_address_uses_first_ldp_address_line_from_container():
    page = FakeAddressPage(
        {
            ".re__ldp-address .re__address": FakeElement(
                "Khu đô thị Nam Thăng Long - Ciputra, Phường Phú Thượng, Quận Tây Hồ, Hà Nội\n"
                "(Phường Phú Thượng, Hà Nội mới)"
            )
        }
    )

    address = extract_listing_address_from_page(page)

    assert (
        address
        == "Khu đô thị Nam Thăng Long - Ciputra, Phường Phú Thượng, Quận Tây Hồ, Hà Nội"
    )


def test_extract_listing_address_falls_back_to_breadcrumb():
    page = FakeAddressPage(
        {
            ".re__breadcrumb": FakeElement(
                children={
                    "a": [
                        FakeElement("Bán"),
                        FakeElement("Hà Nội"),
                        FakeElement("Tây Hồ"),
                        FakeElement("Nhà biệt thự, liền kề tại Khu đô thị Nam Thăng Long - Ciputra"),
                    ]
                }
            )
        }
    )

    address = extract_listing_address_from_page(page)

    assert (
        address
        == "Bán, Hà Nội, Tây Hồ, Nhà biệt thự, liền kề tại Khu đô thị Nam Thăng Long - Ciputra"
    )


def test_extract_listing_property_type_from_breadcrumb_category():
    page = FakeAddressPage(
        {
            ".re__breadcrumb": FakeElement(
                children={
                    "a": [
                        FakeElement("Bán"),
                        FakeElement("Hà Nội"),
                        FakeElement("Tây Hồ"),
                        FakeElement("Nhà biệt thự, liền kề tại Khu đô thị Nam Thăng Long - Ciputra"),
                    ]
                }
            )
        }
    )

    property_type = extract_listing_property_type_from_page(page)

    assert property_type == "Nhà biệt thự, liền kề tại Khu đô thị Nam Thăng Long - Ciputra"


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


class FakeDetailElement:
    def inner_text(self):
        return "Valid listing title"


class FakeDetailPage:
    def __init__(self):
        self.goto_kwargs = None

    def goto(self, url, **kwargs):
        self.goto_kwargs = kwargs

    def query_selector(self, selector):
        if selector in {"h1.re__pr-title", "h1"}:
            return FakeDetailElement()
        return None

    def title(self):
        return "Valid listing title"


class FakeDetailContext:
    def __init__(self, page):
        self.page = page

    def new_page(self):
        return self.page

    def close(self):
        pass


class FakeDetailBrowser:
    def __init__(self, page):
        self.page = page

    def new_context(self, **_kwargs):
        return FakeDetailContext(self.page)


class FakeStealth:
    def apply_stealth_sync(self, _page):
        pass


def _assert_detail_crawler_uses_fast_commit_wait(monkeypatch, module):
    page = FakeDetailPage()
    monkeypatch.setattr(
        module,
        "parse_detail_page",
        lambda _page, url, product_id: {"url": url, "product_id": product_id},
    )

    row = module.crawl_detail(
        FakeDetailBrowser(page),
        "https://batdongsan.com.vn/listing-pr1",
        "pr1",
        FakeStealth(),
        retries=0,
    )

    assert row == {"url": "https://batdongsan.com.vn/listing-pr1", "product_id": "pr1"}
    assert page.goto_kwargs["wait_until"] == "commit"


def test_sale_detail_crawler_uses_fast_commit_wait(monkeypatch):
    _assert_detail_crawler_uses_fast_commit_wait(monkeypatch, sale_crawl_details)


def test_rent_detail_crawler_uses_fast_commit_wait(monkeypatch):
    _assert_detail_crawler_uses_fast_commit_wait(monkeypatch, rent_crawl_details)
