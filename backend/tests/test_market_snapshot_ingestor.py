from datetime import date

from data_pipeline.ingestors.market_snapshot_ingestor import (
    INTERNAL_LISTINGS_SOURCE_NAME,
    aggregate_market_snapshots,
    normalize_hf_market_row,
    normalize_listing_market_row,
)


def test_normalize_hf_market_row_extracts_month_and_price_per_m2():
    row = {
        "name": "Can ho Quan 7",
        "property_type_name": "Căn hộ chung cư",
        "province_name": "Hồ Chí Minh",
        "district_name": "Quận 7",
        "ward_name": "Tân Phú",
        "street_name": "Nguyễn Thị Thập",
        "price": 4_200_000_000,
        "area": 70,
        "published_at": "2026-03-15T08:30:00",
    }

    normalized = normalize_hf_market_row(row)

    assert normalized == {
        "city": "Hồ Chí Minh",
        "district": "Quận 7",
        "ward": "Tân Phú",
        "street": "Nguyễn Thị Thập",
        "property_type": "Căn hộ chung cư",
        "month": date(2026, 3, 1),
        "price": 4_200_000_000.0,
        "area": 70.0,
        "price_per_m2": 60_000_000.0,
    }


def test_normalize_hf_market_row_defaults_missing_street_to_empty():
    row = {
        "property_type_name": "Căn hộ chung cư",
        "province_name": "Hồ Chí Minh",
        "district_name": "Quận 7",
        "ward_name": "Tân Phú",
        "price": 4_200_000_000,
        "area": 70,
        "published_at": "2026-03-15T08:30:00",
    }

    normalized = normalize_hf_market_row(row)

    assert normalized is not None
    assert normalized["street"] == ""


def test_normalize_listing_market_row_converts_listing_units_to_vnd():
    row = {
        "listing_type": "sale",
        "is_active": True,
        "city": "Há»“ ChÃ­ Minh",
        "district": "Quáº­n 7",
        "ward": "TÃ¢n PhÃº",
        "property_type": "CÄƒn há»™ chung cÆ°",
        "price": 4.2,
        "price_unit": "billion",
        "price_per_m2": 60,
        "area": 70,
        "post_date": "15/06/2026",
    }

    normalized = normalize_listing_market_row(row)

    assert normalized == {
        "city": "Há»“ ChÃ­ Minh",
        "district": "Quáº­n 7",
        "ward": "TÃ¢n PhÃº",
        "street": "",
        "property_type": "CÄƒn há»™ chung cÆ°",
        "month": date(2026, 6, 1),
        "price": 4_200_000_000.0,
        "area": 70.0,
        "price_per_m2": 60_000_000.0,
    }


def test_normalize_listing_market_row_skips_rent_and_inactive_rows():
    assert normalize_listing_market_row({"listing_type": "rent", "is_active": True}) is None
    assert normalize_listing_market_row({"listing_type": "sale", "is_active": False}) is None


def test_aggregate_market_snapshots_groups_by_location_type_and_month():
    rows = [
        {
            "city": "Hồ Chí Minh",
            "district": "Quận 7",
            "ward": "Tân Phú",
            "street": "Nguyễn Thị Thập",
            "property_type": "Căn hộ chung cư",
            "month": date(2026, 3, 1),
            "price": 4_000_000_000,
            "area": 80,
            "price_per_m2": 50_000_000,
        },
        {
            "city": "Hồ Chí Minh",
            "district": "Quận 7",
            "ward": "Tân Phú",
            "street": "Nguyễn Thị Thập",
            "property_type": "Căn hộ chung cư",
            "month": date(2026, 3, 1),
            "price": 6_000_000_000,
            "area": 100,
            "price_per_m2": 60_000_000,
        },
        {
            "city": "Hà Nội",
            "district": "Tây Hồ",
            "ward": "",
            "street": "",
            "property_type": "Nhà",
            "month": date(2026, 2, 1),
            "price": 10_000_000_000,
            "area": 50,
            "price_per_m2": 200_000_000,
        },
    ]

    snapshots = aggregate_market_snapshots(rows, source=INTERNAL_LISTINGS_SOURCE_NAME)

    assert len(snapshots) == 2
    first = next(row for row in snapshots if row["city"] == "Hồ Chí Minh")
    assert first["city"] == "Hồ Chí Minh"
    assert first["district"] == "Quận 7"
    assert first["street"] == "Nguyễn Thị Thập"
    assert first["listing_count"] == 2
    assert first["avg_price"] == 5_000_000_000
    assert first["median_price"] == 5_000_000_000
    assert first["avg_price_per_m2"] == 55_000_000
    assert first["median_price_per_m2"] == 55_000_000
    assert first["period"] == "2026-03"
    assert first["source"] == INTERNAL_LISTINGS_SOURCE_NAME


def test_aggregate_market_snapshots_separates_segments_by_street():
    rows = [
        {
            "city": "Hồ Chí Minh",
            "district": "Quận 7",
            "ward": "Tân Phú",
            "street": "Nguyễn Thị Thập",
            "property_type": "Căn hộ chung cư",
            "month": date(2026, 3, 1),
            "price": 4_000_000_000,
            "area": 80,
            "price_per_m2": 50_000_000,
        },
        {
            "city": "Hồ Chí Minh",
            "district": "Quận 7",
            "ward": "Tân Phú",
            "street": "Huỳnh Tấn Phát",
            "property_type": "Căn hộ chung cư",
            "month": date(2026, 3, 1),
            "price": 6_000_000_000,
            "area": 100,
            "price_per_m2": 60_000_000,
        },
    ]

    snapshots = aggregate_market_snapshots(rows)

    assert len(snapshots) == 2
    streets = {row["street"] for row in snapshots}
    assert streets == {"Nguyễn Thị Thập", "Huỳnh Tấn Phát"}
    for row in snapshots:
        assert row["listing_count"] == 1
