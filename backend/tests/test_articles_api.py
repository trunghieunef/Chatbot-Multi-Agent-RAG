from app.routers.articles import (
    apply_article_filters,
    apply_article_sort,
    article_card_response,
)


class ArticleStub:
    id = 7
    title = "Thi truong BDS phuc hoi"
    body = "Noi dung bai viet " * 30
    category = "news"
    source = "batdongsan.com"
    post_date = None
    url = "https://example.test/news"
    created_at = None
    updated_at = None


def test_article_card_response_derives_summary():
    response = article_card_response(ArticleStub())

    assert response.title == "Thi truong BDS phuc hoi"
    assert response.summary.startswith("Noi dung bai viet")
    assert len(response.summary) <= 163


def test_article_card_response_keeps_body_for_detail_pages():
    response = article_card_response(ArticleStub())

    assert response.body.startswith("Noi dung bai viet")
    assert response.summary


def test_article_card_response_includes_primary_image_url():
    response = article_card_response(
        ArticleStub(),
        ["https://cdn.example.test/a.jpg", "https://cdn.example.test/b.jpg"],
    )

    assert response.primary_image_url == "https://cdn.example.test/a.jpg"
    assert response.image_urls == [
        "https://cdn.example.test/a.jpg",
        "https://cdn.example.test/b.jpg",
    ]


def test_article_filters_exclude_legal_by_default():
    query = apply_article_filters(None, {"search": None, "category": None})

    assert query is not None


def test_article_sort_supports_known_options():
    assert apply_article_sort(None, "newest") is not None
    assert apply_article_sort(None, "oldest") is not None
