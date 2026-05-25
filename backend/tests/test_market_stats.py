from chatbot.tools.market_stats import build_district_price_query


def test_build_district_price_query_includes_filters():
    sql, params = build_district_price_query(city="Hồ Chí Minh", listing_type="sale", property_type="apartment")

    assert "AVG(price)" in sql
    assert "AVG(price_per_m2)" in sql
    assert "city = :city" in sql
    assert params == {"city": "Hồ Chí Minh", "listing_type": "sale", "property_type": "%apartment%"}
