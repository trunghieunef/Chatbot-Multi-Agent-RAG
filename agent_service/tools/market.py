from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import async_session

from agent_service.tools.market_stats import district_price_overview


async def lookup_market_metrics(filters: dict[str, Any]) -> list[dict[str, Any]]:
    """Current snapshot lookup (existing tool)."""
    city = filters.get("city")
    listing_type = filters.get("listing_type") or "sale"
    property_type = filters.get("property_type")
    district = filters.get("district")
    if not city:
        return []

    rows = await district_price_overview(
        city=str(city),
        listing_type=str(listing_type),
        property_type=str(property_type) if property_type else None,
        district=str(district) if district else None,
    )
    return [
        {
            "source_identity": (
                f"market:{row.get('district')}:{property_type or 'all'}:"
                f"avg_price_per_m2:{row.get('period') or 'current'}"
            ),
            "metric": "avg_price_per_m2",
            "value": row.get("avg_price_per_m2"),
            "unit": "million VND/m2",
            "location": {"city": city, "district": row.get("district")},
            "property_type": property_type,
            "period": row.get("period") or "current_snapshot",
            "record": row,
        }
        for row in rows
        if row.get("avg_price_per_m2") is not None
    ]


async def lookup_market_timeseries(
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Fetch timeseries from market_price_snapshots for trend analysis.

    Returns one dict per month with aggregated price metrics.
    Fields: snapshot_month, avg_price_per_m2, median_price_per_m2,
            min_price_per_m2, max_price_per_m2, listing_count.
    """
    city = filters.get("city")
    if not city:
        return []

    district = filters.get("district")
    property_type = filters.get("property_type")
    months = int(filters.get("months", 6))

    clauses = [
        "city ILIKE :city",
        "month >= (DATE_TRUNC('month', NOW()) - :interval)::date",
    ]
    params: dict[str, Any] = {
        "city": f"%{city}%",
        "interval": timedelta(days=months * 31),
    }

    if district:
        clauses.append("district ILIKE :district")
        params["district"] = f"%{district}%"
    if property_type:
        clauses.append("property_type ILIKE :property_type")
        params["property_type"] = f"%{property_type}%"

    sql = (
        "SELECT "
        "  TO_CHAR(month, 'YYYY-MM') AS snapshot_month, "
        "  city, district, property_type, "
        "  SUM(listing_count) AS listing_count, "
        "  ROUND(AVG(avg_price_per_m2)::numeric, 2) AS avg_price_per_m2, "
        "  ROUND(AVG(median_price_per_m2)::numeric, 2) AS median_price_per_m2, "
        "  ROUND(MIN(avg_price_per_m2)::numeric, 2) AS min_price_per_m2, "
        "  ROUND(MAX(avg_price_per_m2)::numeric, 2) AS max_price_per_m2 "
        "FROM market_price_snapshots "
        f"WHERE {' AND '.join(clauses)} "
        "GROUP BY snapshot_month, city, district, property_type "
        "ORDER BY snapshot_month ASC"
    )

    async with async_session() as session:
        result = await session.execute(text(sql), params)
        return [
            {
                "snapshot_month": row.snapshot_month,
                "city": row.city,
                "district": row.district,
                "property_type": row.property_type,
                "listing_count": row.listing_count,
                "avg_price_per_m2": float(row.avg_price_per_m2) if row.avg_price_per_m2 else None,
                "median_price_per_m2": float(row.median_price_per_m2) if row.median_price_per_m2 else None,
                "min_price_per_m2": float(row.min_price_per_m2) if row.min_price_per_m2 else None,
                "max_price_per_m2": float(row.max_price_per_m2) if row.max_price_per_m2 else None,
            }
            for row in result
        ]
