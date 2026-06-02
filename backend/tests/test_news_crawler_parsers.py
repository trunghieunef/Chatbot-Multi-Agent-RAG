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
