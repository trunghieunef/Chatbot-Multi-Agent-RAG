from pathlib import Path

from crawler.projects import crawl_details, crawl_urls


FIXTURES = Path(__file__).parent / "fixtures"


def test_project_listing_fixture_extracts_urls():
    html = (FIXTURES / "project_listing_sample.html").read_text(encoding="utf-8")
    urls = crawl_urls.extract_project_urls(html, base_url="https://batdongsan.com.vn")

    assert len(urls) >= 2
    assert all(url.startswith("https://batdongsan.com.vn/") for url in urls)
    assert len(urls) == len(set(urls))


def test_project_listing_only_extracts_urls_from_main_left_container():
    html = """
    <html>
      <body>
        <nav>
          <a href="/du-an-can-ho-chung-cu">Category link should be ignored</a>
        </nav>
        <section class="re__project-main-left">
          <a href="/du-an-can-ho-chung-cu-quan-7/the-peak-garden-pj3029">
            The Peak Garden
          </a>
          <a href="/du-an-khu-nghi-duong-sinh-thai-ha-long-qni/sun-festo-town-pj6731">
            Sun Festo Town
          </a>
        </section>
      </body>
    </html>
    """

    urls = crawl_urls.extract_project_urls(html, base_url="https://batdongsan.com.vn")

    assert urls == [
        "https://batdongsan.com.vn/du-an-can-ho-chung-cu-quan-7/the-peak-garden-pj3029",
        "https://batdongsan.com.vn/du-an-khu-nghi-duong-sinh-thai-ha-long-qni/sun-festo-town-pj6731",
    ]


def test_project_detail_fixture_extracts_ingestor_compatible_record():
    html = (FIXTURES / "project_detail_sample.html").read_text(encoding="utf-8")
    record = crawl_details.parse_project_detail(
        html,
        url="https://batdongsan.com.vn/du-an/example-project",
    )

    assert record["slug"] == "example-project"
    assert record["name"]
    assert "developer" in record
    assert "district" in record
    assert "city" in record
    assert "status" in record
    assert "price_range" in record
    assert "area_range" in record
    assert "project_type" in record
    assert "description" in record
    assert "amenities" in record
    assert record["url"].startswith("https://batdongsan.com.vn/")


def test_project_detail_extracts_batdongsan_project_dom():
    html = (FIXTURES / "project_detail_batdongsan_sample.html").read_text(encoding="utf-8")
    record = crawl_details.parse_project_detail(
        html,
        url="https://batdongsan.com.vn/du-an-khu-nghi-duong-sinh-thai-ha-long-qni/sun-festo-town-pj6731",
    )

    assert record["slug"] == "sun-festo-town"
    assert record["name"] == "Sun Festo Town"
    assert record["developer"] == "Tập đoàn Sun Group"
    assert record["location"] == "Phường Bãi Cháy, Thành phố Hạ Long, Quảng Ninh."
    assert record["area_range"] == "1,07 ha"
    assert "Tổ hợp nhà phố thương mại" in record["description"]
    assert "Vị Trí" in record["description"]
    assert "Hồ bơi 4 mùa" in record["amenities"]


def test_project_detail_page_preserves_input_slug():
    class PageStub:
        def content(self):
            return (FIXTURES / "project_detail_sample.html").read_text(encoding="utf-8")

    record = crawl_details.parse_detail_page(
        PageStub(),
        url="https://batdongsan.com.vn/du-an/url-slug",
        slug="url-slug",
    )

    assert record["slug"] == "url-slug"
