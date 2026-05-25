from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import async_session


def build_district_price_query(*, city: str, listing_type: str, property_type: str | None = None) -> tuple[str, dict]:
    """Build a SQL query that aggregates listing prices by district.

    Returns (sql, params). Caller passes ``params`` as bind params; values
    are never interpolated. Use with ``sqlalchemy.text(sql)``.
    """
    clauses = [
        "is_active = true",
        "city = :city",
        "listing_type = :listing_type",
        "price IS NOT NULL",
    ]
    params: dict = {"city": city, "listing_type": listing_type}
    if property_type:
        clauses.append("property_type ILIKE :property_type")
        params["property_type"] = f"%{property_type}%"

    sql = (
        "SELECT district, COUNT(*) AS listings, "
        "AVG(price) AS avg_price, AVG(price_per_m2) AS avg_price_per_m2 "
        "FROM listings "
        f"WHERE {' AND '.join(clauses)} "
        "GROUP BY district "
        "ORDER BY avg_price_per_m2 DESC NULLS LAST"
    )
    return sql, params


async def district_price_overview(city: str, listing_type: str, property_type: str | None = None) -> list[dict]:
    sql, params = build_district_price_query(city=city, listing_type=listing_type, property_type=property_type)
    async with async_session() as session:
        result = await session.execute(text(sql), params)
        return [dict(row._mapping) for row in result.all()]
