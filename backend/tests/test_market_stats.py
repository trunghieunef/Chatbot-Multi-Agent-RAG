from chatbot.tools.market_stats import build_district_price_query, build_snapshot_district_price_query
import pytest


class _FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _FakeRowsResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _FakeOneResult:
    def __init__(self, row):
        self.row = row

    def one(self):
        return self.row


def test_build_district_price_query_includes_filters():
    sql, params = build_district_price_query(
        city="Ho Chi Minh",
        listing_type="sale",
        property_type="apartment",
        district="Quan 7",
    )

    assert "AVG(price)" in sql
    assert "AVG(price_per_m2)" in sql
    assert "unaccent(city) ILIKE unaccent(:city)" in sql
    assert "unaccent(district) ILIKE unaccent(:district)" in sql
    assert params == {
        "city": "Ho Chi Minh",
        "listing_type": "sale",
        "property_type": "%apartment%",
        "district": "%Quan 7%",
    }


def test_build_snapshot_district_price_query_uses_market_snapshots():
    sql, params = build_snapshot_district_price_query(
        city="Hồ Chí Minh",
        property_type="Căn hộ",
        district="Quận 7",
    )

    assert "FROM market_price_snapshots" in sql
    assert "source = :preferred_source" in sql
    assert "source = (SELECT source FROM selected_source)" in sql
    assert "unaccent(city) ILIKE unaccent(:city)" in sql
    assert "unaccent(district) ILIKE unaccent(:district)" in sql
    assert params == {
        "city": "Hồ Chí Minh",
        "property_type": "%Căn hộ%",
        "district": "%Quận 7%",
        "preferred_source": "internal:listings",
    }


def test_market_stats_estimates_negative_pg_stats_distinct_ratio():
    from app.routers.market import _estimate_distinct_count

    assert _estimate_distinct_count(total_listings=1000, n_distinct=-0.25) == 250


@pytest.mark.asyncio
async def test_market_stats_uses_ttl_cache():
    from app.routers import market

    market._market_stats_cache.clear()
    execute_calls = 0
    results = [
        _FakeScalarResult(100),
        _FakeRowsResult([("city", 2.0), ("district", 5.0)]),
        _FakeOneResult((3.5, 70.0, 70, 30, 100)),
    ]

    class FakeSession:
        async def execute(self, statement):
            nonlocal execute_calls
            result = results[execute_calls]
            execute_calls += 1
            return result

    first = await market.get_market_stats(db=FakeSession())
    second = await market.get_market_stats(db=FakeSession())

    assert first == second
    assert first == {
        "total_listings": 100,
        "average_price_billion": 3.5,
        "average_area_m2": 70.0,
        "listings_for_sale": 70,
        "listings_for_rent": 30,
        "total_cities": 2,
        "total_districts": 5,
    }
    assert execute_calls == 3
