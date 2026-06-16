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
          <a href="/du-an-bat-dong-san">All projects index should be ignored</a>
          <a href="/du-an-can-ho-chung-cu">Category link inside content should be ignored</a>
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


def test_project_detail_page_rejects_shell_domain_heading():
    class PageStub:
        def content(self):
            return """
            <html>
              <head><title>batdongsan.com.vn</title></head>
              <body>
                <h1>batdongsan.com.vn</h1>
                <p>Vui lòng chờ trong giây lát...</p>
              </body>
            </html>
            """

    record = crawl_details.parse_detail_page(
        PageStub(),
        url="https://batdongsan.com.vn/du-an-shophouse-gia-lam/malibu-walk-pj6756",
        slug="malibu-walk-pj6756",
    )

    assert record is None


def test_project_detail_extracts_live_detail_sections():
    html = """
    <html>
      <body>
        <div class="project-main-container">
          <h1 class="re__project-name">Khu nhà ở thương mại Vạn Xuân</h1>
          <div class="re__project-address">
            Phường Xuân Đỉnh, Quận Bắc Từ Liêm, Hà Nội.
            <a>Xem bản đồ</a>
          </div>
          <div class="re__project-album">
            <img src="https://file4.batdongsan.com.vn/project-1.jpg" alt="Khu nhà ở thương mại Vạn Xuân">
            <img data-src="https://file4.batdongsan.com.vn/project-2.jpg">
          </div>
          <div class="re__prj-tag-info re__project-open">Đang mở bán</div>
        </div>
        <div class="re__project-main-left">
          <div class="re__project-main-number">
            <table>
              <tbody class="re__project-attr">
                <tr>
                  <td class="re__attr-item-label"><h4>Số căn</h4></td>
                  <td class="re__attr-item-value">37 căn</td>
                </tr>
              </tbody>
              <tbody class="re__project-attr">
                <tr>
                  <td class="re__attr-item-label"><h4>Diện tích</h4></td>
                  <td class="re__attr-item-value">3.198,8 m²</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="js__prj-detail-content re__detail-content re__project-editor">
            <p>Dự án gồm 37 căn biệt thự được thiết kế hiện đại.</p>
            <h3>Mặt Bằng - Thiết Kế</h3>
            <p>Loại hình sản phẩm: Biệt thự</p>
            <p>Pháp lý: Sổ đỏ sở hữu lâu dài</p>
          </div>
          <div class="re__project-toogle-box">
            <div class="re__project-box-item">
              <span>Số căn</span><span>37 căn</span>
            </div>
            <div class="re__project-box-item">
              <span>Quy mô</span><span>37 căn biệt thự</span>
            </div>
            <div class="re__prj-facilities">
              <div class="re__toogle-detail">
                <span>Bãi đỗ xe</span><span>Đường chạy bộ</span>
              </div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """

    record = crawl_details.parse_project_detail(
        html,
        url="https://batdongsan.com.vn/du-an-biet-thu-lien-ke-bac-tu-liem/khu-nha-o-thuong-mai-van-xuan-pj6342",
    )

    assert record["name"] == "Khu nhà ở thương mại Vạn Xuân"
    assert record["status"] == "Đang mở bán"
    assert record["total_units"] == "37"
    assert record["area_range"] == "3.198,8 m²"
    assert record["scale"] == "37 căn biệt thự"
    assert record["project_type"] == "Biệt thự"
    assert record["legal"] == "Sổ đỏ sở hữu lâu dài"
    assert record["amenities"] == '["Bãi đỗ xe", "Đường chạy bộ"]'
    assert record["image_urls"] == (
        '["https://file4.batdongsan.com.vn/project-1.jpg", '
        '"https://file4.batdongsan.com.vn/project-2.jpg"]'
    )


def test_project_detail_infers_fields_from_live_description():
    html = """
    <html>
      <body>
        <div class="project-main-container">
          <h1 class="re__project-name">Malibu Walk</h1>
          <div class="re__project-address">Xã Đa Tốn, Huyện Gia Lâm, Hà Nội.</div>
          <div class="re__prj-tag-info re__project-open">Đang mở bán</div>
        </div>
        <div class="js__prj-detail-content re__detail-content re__project-editor">
          <p>Malibu Walk là tuyến phố đi bộ và shophouse thương mại cao cấp nằm tại tâm điểm phân khu Masteri Waterfront thuộc Khu đô thị Vinhomes Ocean Park 1 (Gia Lâm, Hà Nội) được phát triển bởi Masterise Homes.</p>
          <p>Với tổng diện tích khoảng 7,3ha, Malibu Walk được định hướng trở thành tâm điểm thương mại - dịch vụ - giải trí cao cấp.</p>
          <p>Malibu Walk gồm 3 dãy shophouse cao 5 tầng với số lượng 60 căn.</p>
        </div>
      </body>
    </html>
    """

    record = crawl_details.parse_project_detail(
        html,
        url="https://batdongsan.com.vn/du-an-shophouse-gia-lam/malibu-walk-pj6756",
    )

    assert record["developer"] == "Masterise Homes"
    assert record["area_range"] == "7,3ha"
    assert record["total_units"] == "60"
    assert record["project_type"] == "Shophouse"
