from pathlib import Path

from crawler.news import crawl_articles
from crawler.core.csv_writer import append_csv


FIXTURES = Path(__file__).parent / "fixtures"


def test_news_listing_fixture_extracts_urls():
    html = (FIXTURES / "news_listing_sample.html").read_text(encoding="utf-8")
    urls = crawl_articles.extract_article_urls(html, base_url="https://batdongsan.com.vn")

    assert len(urls) >= 2
    assert all(url.startswith("https://batdongsan.com.vn/") for url in urls)
    assert len(urls) == len(set(urls))


def test_news_article_fixture_extracts_ingestor_compatible_record():
    html = (FIXTURES / "news_article_sample.html").read_text(encoding="utf-8")
    record = crawl_articles.parse_article(
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
    record = crawl_articles.parse_article(
        html,
        url="https://batdongsan.com.vn/tin-tuc/example-article",
    )
    output = tmp_path / "news_articles.csv"

    append_csv(str(output), [record], crawl_articles.FIELDS)

    assert output.read_text(encoding="utf-8-sig").splitlines()[0].split(",") == crawl_articles.FIELDS


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

    record = crawl_articles.parse_article(
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
