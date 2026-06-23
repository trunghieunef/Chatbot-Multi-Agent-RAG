from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import async_session


def build_district_price_query(
    *,
    city: str,
    listing_type: str,
    property_type: str | None = None,
    district: str | None = None,
) -> tuple[str, dict]:
    """Build a SQL query that aggregates listing prices by district.

    Returns (sql, params). Caller passes ``params`` as bind params; values
    are never interpolated. Use with ``sqlalchemy.text(sql)``.
    """
    clauses = [
        "is_active = true",
        "unaccent(city) ILIKE unaccent(:city)",
        "listing_type = :listing_type",
        "price IS NOT NULL",
    ]
    params: dict = {"city": city, "listing_type": listing_type}
    if property_type:
        clauses.append("property_type ILIKE :property_type")
        params["property_type"] = f"%{property_type}%"
    if district:
        clauses.append("unaccent(district) ILIKE unaccent(:district)")
        params["district"] = f"%{district}%"

    sql = (
        "SELECT district, COUNT(*) AS listings, "
        "AVG(price) AS avg_price, AVG(price_per_m2) AS avg_price_per_m2 "
        "FROM listings "
        f"WHERE {' AND '.join(clauses)} "
        "GROUP BY district "
        "ORDER BY avg_price_per_m2 DESC NULLS LAST"
    )
    return sql, params


def build_snapshot_district_price_query(
    *,
    city: str,
    property_type: str | None = None,
    district: str | None = None,
    preferred_source: str = "internal:listings",
) -> tuple[str, dict]:
    """Build a SQL query that reads the latest market snapshot by district."""
    clauses = [
        "unaccent(city) ILIKE unaccent(:city)",
        "source = (SELECT source FROM selected_source)",
        "month = (SELECT month FROM selected_source)",
    ]
    params: dict = {"city": city, "preferred_source": preferred_source}
    if property_type:
        clauses.append("property_type ILIKE :property_type")
        params["property_type"] = f"%{property_type}%"
    if district:
        clauses.append("unaccent(district) ILIKE unaccent(:district)")
        params["district"] = f"%{district}%"

    sql = (
        "WITH selected_source AS ("
        "SELECT source, MAX(month) AS month "
        "FROM market_price_snapshots "
        "WHERE unaccent(city) ILIKE unaccent(:city) "
        "GROUP BY source "
        "ORDER BY CASE WHEN source = :preferred_source THEN 0 ELSE 1 END, MAX(month) DESC "
        "LIMIT 1"
        ") "
        "SELECT district, SUM(listing_count) AS listings, "
        "SUM(avg_price * listing_count) / NULLIF(SUM(listing_count), 0) AS avg_price_vnd, "
        "SUM(avg_price_per_m2 * listing_count) / NULLIF(SUM(listing_count), 0) AS avg_price_per_m2_vnd, "
        "MAX(period) AS period "
        "FROM market_price_snapshots "
        f"WHERE {' AND '.join(clauses)} "
        "GROUP BY district "
        "ORDER BY avg_price_per_m2_vnd DESC NULLS LAST"
    )
    return sql, params


def _convert_snapshot_rows(rows: list[dict]) -> list[dict]:
    converted: list[dict] = []
    for row in rows:
        avg_price_vnd = row.get("avg_price_vnd")
        avg_price_per_m2_vnd = row.get("avg_price_per_m2_vnd")
        converted.append(
            {
                "district": row.get("district"),
                "listings": row.get("listings"),
                "avg_price": (float(avg_price_vnd) / 1_000_000_000) if avg_price_vnd is not None else None,
                "avg_price_per_m2": (
                    float(avg_price_per_m2_vnd) / 1_000_000
                    if avg_price_per_m2_vnd is not None
                    else None
                ),
                "period": row.get("period"),
                "source": "market_price_snapshots",
            }
        )
    return converted


async def district_price_overview(
    city: str,
    listing_type: str,
    property_type: str | None = None,
    district: str | None = None,
) -> list[dict]:
    if listing_type == "sale":
        snapshot_sql, snapshot_params = build_snapshot_district_price_query(
            city=city,
            property_type=property_type,
            district=district,
        )
        async with async_session() as session:
            result = await session.execute(text(snapshot_sql), snapshot_params)
            snapshot_rows = [dict(row._mapping) for row in result.all()]
        if snapshot_rows:
            return _convert_snapshot_rows(snapshot_rows)

    sql, params = build_district_price_query(
        city=city,
        listing_type=listing_type,
        property_type=property_type,
        district=district,
    )
    async with async_session() as session:
        result = await session.execute(text(sql), params)
        return [dict(row._mapping) for row in result.all()]
