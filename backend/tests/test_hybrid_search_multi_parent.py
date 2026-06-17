from chatbot.tools.hybrid_search import build_project_filter_clauses, build_article_filter_clauses


def test_build_project_filter_clauses_supports_status_and_city():
    clauses, params = build_project_filter_clauses({"status": "selling", "city": "Ho Chi Minh"})

    sql = " ".join(clauses)
    assert "status = :status" in sql
    assert "unaccent(lower(city)) LIKE :city_norm" in sql
    assert params["city_norm"] == "%ho chi minh%"


def test_build_article_filter_clauses_supports_category():
    clauses, params = build_article_filter_clauses({"category": "news"})

    assert "category = :category" in " ".join(clauses)
    assert params["category"] == "news"
