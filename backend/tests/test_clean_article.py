from datetime import date

from data_pipeline.clean import row_to_article


def test_row_to_article_parses_iso_date():
    row = {
        "title": "Thị trường BĐS quý 1 2026",
        "body": "Báo cáo thị trường...",
        "category": "news",
        "post_date": "2026-04-15",
        "url": "https://batdongsan.com.vn/tin-tuc/q1-2026",
    }

    article = row_to_article(row)

    assert article["title"] == "Thị trường BĐS quý 1 2026"
    assert article["category"] == "news"
    assert article["post_date"] == date(2026, 4, 15)


def test_row_to_article_returns_none_post_date_for_invalid_input():
    article = row_to_article({"title": "T", "body": "B", "url": "u", "post_date": "không rõ"})
    assert article["post_date"] is None


def test_row_to_article_passes_through_explicit_source():
    article = row_to_article(
        {"title": "T", "body": "B", "url": "u", "source": "luatvietnam.vn", "category": "legal"}
    )
    assert article["source"] == "luatvietnam.vn"
    assert article["category"] == "legal"


def test_row_to_article_defaults_source_when_missing():
    article = row_to_article({"title": "T", "body": "B", "url": "u"})
    assert article["source"] == "batdongsan.com"
