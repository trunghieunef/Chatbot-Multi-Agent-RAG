from pathlib import Path

from crawler.news import crawl_articles, crawl_details, crawl_urls
from crawler.core.csv_writer import append_csv


FIXTURES = Path(__file__).parent / "fixtures"


def test_news_listing_fixture_extracts_urls():
    html = (FIXTURES / "news_listing_sample.html").read_text(encoding="utf-8")
    urls = crawl_urls.extract_article_urls(html, base_url="https://batdongsan.com.vn")

    assert len(urls) >= 2
    assert all(url.startswith("https://batdongsan.com.vn/") for url in urls)
    assert len(urls) == len(set(urls))


def test_news_url_parser_output_matches_csv_fields(tmp_path):
    html = (FIXTURES / "news_listing_sample.html").read_text(encoding="utf-8")
    rows = crawl_urls.parse_article_listing(html, base_url="https://batdongsan.com.vn")
    output = tmp_path / "news_urls.csv"

    append_csv(str(output), rows, crawl_urls.FIELDS)

    assert crawl_urls.FIELDS == ["url"]
    assert output.read_text(encoding="utf-8-sig").splitlines()[0] == "url"


def test_news_url_parser_ignores_non_article_links():
    html = """
    <html>
      <body>
        <nav>
          <a href="/tin-tuc">Tin tức index</a>
          <a href="/tin-tuc/thi-truong">Category page</a>
          <a href="/tin-tuc/bat-dong-san-ha-noi">Local news page</a>
          <a href="/wiki">Wiki index</a>
          <a href="/wiki/tac-gia/huongvl">Author profile</a>
        </nav>
        <main>
          <a href="/tin-tuc/bat-dong-san-ha-noi">Local news page in content</a>
          <a href="/tin-tuc/thi-truong/example-123">Market article</a>
          <a href="https://wiki.batdongsan.com.vn/tin-tuc/example-854722">Wiki article</a>
        </main>
      </body>
    </html>
    """

    urls = crawl_urls.extract_article_urls(html, base_url="https://batdongsan.com.vn")

    assert urls == [
        "https://batdongsan.com.vn/tin-tuc/thi-truong/example-123",
        "https://wiki.batdongsan.com.vn/tin-tuc/example-854722",
    ]


def test_news_article_fixture_extracts_ingestor_compatible_record():
    html = (FIXTURES / "news_article_sample.html").read_text(encoding="utf-8")
    record = crawl_details.parse_article(
        html,
        url="https://batdongsan.com.vn/tin-tuc/example-article",
    )

    assert record["title"]
    assert len(record["body"]) > 100
    assert record["category"] in {"news", "legal", "guide", "market"}
    assert record["source"] == "batdongsan.com"
    assert "post_date" in record
    assert record["url"].startswith("https://batdongsan.com.vn/")


def test_news_article_parser_output_matches_csv_fields(tmp_path):
    html = (FIXTURES / "news_article_sample.html").read_text(encoding="utf-8")
    record = crawl_details.parse_article(
        html,
        url="https://batdongsan.com.vn/tin-tuc/example-article",
    )
    output = tmp_path / "news_articles.csv"

    append_csv(str(output), [record], crawl_details.FIELDS)

    assert output.read_text(encoding="utf-8-sig").splitlines()[0].split(",") == crawl_details.FIELDS


def test_news_article_extracts_live_wiki_article_metadata():
    html = """
    <html>
      <body>
        <main>
          <h1>Văn Phú Công Bố Thước Đo Chuẩn Sống Mới</h1>
          <a href="/wiki/tac-gia/huongvl">Lan Chi</a>
          <span>Được đăng bởi</span>
          <a href="/wiki/tac-gia/huongvl">Lan Chi</a>
          <span>Cập nhật lần cuối vào</span>
          <span>28/05/2026 16:00</span>
          <span> • </span>
          <span>Đọc trong khoảng 5 phút</span>
          <img src="https://img.iproperty.com.my/angel/article-1.jpg" alt="Ảnh bài viết">
          <p>Dự án Vlasta Premier - Phú Thuận đã chính thức ra mắt trong sự kiện diễn ra vào chiều ngày 27/5.</p>
          <p>Được tổ chức tại GEM Center, lễ ra mắt dự án diễn ra trong không gian đầy cảm hứng.</p>
          <figure>
            <img data-src="https://img.iproperty.com.my/angel/article-2.jpg">
            <figcaption>Sân khấu nghệ thuật kết hợp công nghệ.</figcaption>
          </figure>
          <p>Với triết lý phát triển bất động sản vị nhân sinh, dự án được kỳ vọng là điểm sáng mới.</p>
          <h2>Chia sẻ bài viết này</h2>
          <p>Footer text must not be included.</p>
        </main>
      </body>
    </html>
    """

    record = crawl_details.parse_article(
        html,
        url="https://wiki.batdongsan.com.vn/tin-tuc/example-854722",
    )

    assert record["title"] == "Văn Phú Công Bố Thước Đo Chuẩn Sống Mới"
    assert record["author"] == "Lan Chi"
    assert record["post_date"] == "28/05/2026 16:00"
    assert record["reading_time"] == "Đọc trong khoảng 5 phút"
    assert record["summary"].startswith("Dự án Vlasta Premier")
    assert "Footer text must not be included" not in record["body"]
    assert "Sân khấu nghệ thuật kết hợp công nghệ." in record["body"]
    assert record["image_urls"] == (
        '["https://img.iproperty.com.my/angel/article-1.jpg", '
        '"https://img.iproperty.com.my/angel/article-2.jpg"]'
    )


def test_news_article_extracts_nextjs_author_info_post_date():
    html = """
    <html>
      <body>
        <div class="ArticlePageTemplate_articlePageContainer__wcRoZ container">
          <h1>Sự Kiện Toàn Cảnh Thị Trường BĐS 6 Tháng Đầu Năm 2026</h1>
          <div class="AuthorInfo_authorInfo__2Zax_">
            <div class="AuthorInfo_authorName__m9KD3">Được đăng bởi Lan Chi</div>
            <div class="AuthorInfo_postDate__UTKIr">Cập nhật lần cuối vào 15/06/2026 11:00 • Đọc trong khoảng 4 phút</div>
          </div>
          <div class="content-wrapper">
            <div class="p">Ngày 14/7 tại TP. Hồ Chí Minh và 16/7 tại Hà Nội, Batdongsan.com.vn sẽ tổ chức sự kiện.</div>
            <div class="p">Chương trình quy tụ chuyên gia kinh tế và bất động sản hàng đầu.</div>
          </div>
        </div>
      </body>
    </html>
    """

    record = crawl_details.parse_article(
        html,
        url="https://wiki.batdongsan.com.vn/tin-tuc/su-kien-toan-canh-thi-truong-bds-6-thang-dau-nam-2026-855217",
    )

    assert record["post_date"] == "15/06/2026 11:00"


def test_news_article_does_not_parse_body_as_post_date():
    html = """
    <html>
      <body>
        <main>
          <h1>Lợi thế giá trị sống dài hạn</h1>
          <section class="date">
            <p>Khi lựa chọn nơi an cư cho chặng đường 10-15 năm tới, môi trường sống xung quanh đóng vai trò quan trọng.</p>
            <p>Tác giả: Châu Anh Nguồn tin: Báo Văn hóa Thời gian xuất bản: 07h00 ngày 13/6/2026</p>
          </section>
          <span>Cập nhật lần cuối vào</span>
          <span>14/06/2026 09:30</span>
          <p>Arcadia at Lavila thuộc Lavila Township tại Nam Sài Gòn.</p>
          <p>Hệ tiện ích và cộng đồng cư dân đã vận hành tạo giá trị sống bền vững.</p>
        </main>
      </body>
    </html>
    """

    record = crawl_details.parse_article(
        html,
        url="https://batdongsan.com.vn/tin-tuc/loi-the-gia-tri-song-855022",
    )

    assert record["post_date"] == "14/06/2026 09:30"
    assert len(record["post_date"]) < 30


def test_news_article_extracts_source_publish_time_when_update_date_missing():
    html = """
    <html>
      <body>
        <main>
          <h1>Lợi thế giá trị sống dài hạn</h1>
          <p>Arcadia at Lavila thuộc Lavila Township tại Nam Sài Gòn.</p>
          <p>Tác giả: Châu Anh Nguồn tin: Báo Văn hóa Thời gian xuất bản: 07h00 ngày 13/6/2026</p>
        </main>
      </body>
    </html>
    """

    record = crawl_details.parse_article(
        html,
        url="https://batdongsan.com.vn/tin-tuc/loi-the-gia-tri-song-855022",
    )

    assert record["post_date"] == "13/6/2026 07:00"


def test_news_article_body_uses_content_paragraph_divs_not_image_captions():
    html = """
    <html>
      <body>
        <article>
          <h1>Lợi thế giá trị sống dài hạn</h1>
          <div class="content-wrapper">
            <div class="p"><strong>Khi lựa chọn nơi an cư</strong>, môi trường sống xung quanh đóng vai trò quan trọng không kém căn hộ.</div>
            <figure>
              <img src="https://example.test/article.jpg">
              <figcaption><em>Arcadia at Lavila thuộc Lavila Township tại Nam Sài Gòn.</em></figcaption>
            </figure>
            <h2>Township - Hệ sinh thái sống đồng bộ</h2>
            <div class="p">Township là một khu đô thị được quy hoạch tổng thể với quy mô lớn.</div>
            <h2>Chia sẻ bài viết này</h2>
            <div class="p">Footer text must not be included.</div>
          </div>
        </article>
      </body>
    </html>
    """

    record = crawl_details.parse_article(
        html,
        url="https://batdongsan.com.vn/tin-tuc/loi-the-gia-tri-song-855022",
    )

    assert "Khi lựa chọn nơi an cư" in record["body"]
    assert "Township - Hệ sinh thái sống đồng bộ" in record["body"]
    assert "Township là một khu đô thị" in record["body"]
    assert "Arcadia at Lavila thuộc Lavila Township" not in record["body"]
    assert "Footer text must not be included" not in record["body"]
    assert record["summary"].startswith("Khi lựa chọn nơi an cư")
