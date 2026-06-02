"""Shared listing aggregates for chatbot market and investment agents."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.listing import Listing


def _apply_listing_filters(statement, filters: dict[str, Any]):
    if filters.get("city"):
        statement = statement.where(Listing.city.ilike(f"%{filters['city']}%"))
    if filters.get("district"):
        statement = statement.where(Listing.district.ilike(f"%{filters['district']}%"))
    if filters.get("listing_type"):
        statement = statement.where(Listing.listing_type == filters["listing_type"])
    if filters.get("property_type"):
        statement = statement.where(Listing.property_type.ilike(f"%{filters['property_type']}%"))
    return statement


async def get_market_snapshot(db: AsyncSession, filters: dict[str, Any]) -> dict[str, Any]:
    """Return aggregate listing statistics for a filtered segment."""
    statement = select(
        func.count(Listing.id),
        func.avg(Listing.price),
        func.avg(Listing.area),
        func.avg(Listing.price_per_m2),
    ).where(Listing.is_active == True)  # noqa: E712
    statement = _apply_listing_filters(statement, filters)
    total, avg_price, avg_area, avg_price_per_m2 = (await db.execute(statement)).one()
    return {
        "count": total or 0,
        "avg_price": float(avg_price) if avg_price is not None else None,
        "avg_area": float(avg_area) if avg_area is not None else None,
        "avg_price_per_m2": float(avg_price_per_m2) if avg_price_per_m2 is not None else None,
    }


async def get_district_comparison(
    db: AsyncSession,
    filters: dict[str, Any],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return top district aggregates for comparison within the same segment."""
    scoped_filters = dict(filters)
    scoped_filters.pop("district", None)
    statement = (
        select(
            Listing.district,
            func.count(Listing.id).label("count"),
            func.avg(Listing.price).label("avg_price"),
            func.avg(Listing.price_per_m2).label("avg_price_per_m2"),
        )
        .where(Listing.is_active == True, Listing.district.isnot(None))  # noqa: E712
        .group_by(Listing.district)
        .order_by(func.count(Listing.id).desc())
        .limit(limit)
    )
    statement = _apply_listing_filters(statement, scoped_filters)
    rows = (await db.execute(statement)).all()
    return [
        {
            "district": row[0],
            "count": row[1] or 0,
            "avg_price": float(row[2]) if row[2] is not None else None,
            "avg_price_per_m2": float(row[3]) if row[3] is not None else None,
        }
        for row in rows
    ]
