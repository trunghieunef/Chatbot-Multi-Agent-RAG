"""
Market data and analytics API router.
"""

import time
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, case, literal_column, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.listing import Listing

router = APIRouter(prefix="/market", tags=["Market Data"])

MARKET_STATS_TTL_SECONDS = 300
_market_stats_cache: dict[str, Any] = {}
_market_query_cache: dict[tuple[Any, ...], dict[str, Any]] = {}


def _cached_market_data(cache: dict[str, Any]) -> dict[str, Any] | None:
    expires_at = float(cache.get("expires_at") or 0.0)
    if expires_at > time.monotonic():
        data = cache.get("data")
        if isinstance(data, dict):
            return data
    return None


def _store_market_data(cache: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    cache["data"] = data
    cache["expires_at"] = time.monotonic() + MARKET_STATS_TTL_SECONDS
    return data


def _cached_market_stats() -> dict[str, Any] | None:
    return _cached_market_data(_market_stats_cache)


def _store_market_stats(data: dict[str, Any]) -> dict[str, Any]:
    return _store_market_data(_market_stats_cache, data)


def _cached_market_query(key: tuple[Any, ...]) -> dict[str, Any] | None:
    cache = _market_query_cache.get(key)
    if cache is None:
        return None
    return _cached_market_data(cache)


def _store_market_query(key: tuple[Any, ...], data: dict[str, Any]) -> dict[str, Any]:
    cache = _market_query_cache.setdefault(key, {})
    return _store_market_data(cache, data)


def _positive_int(value: Any) -> int:
    try:
        number = int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0
    return max(number, 0)


def _estimate_distinct_count(*, total_listings: int, n_distinct: Any) -> int:
    try:
        distinct_value = float(n_distinct or 0)
    except (TypeError, ValueError):
        return 0
    if distinct_value < 0:
        return _positive_int(abs(distinct_value) * total_listings)
    return _positive_int(distinct_value)


def _estimate_listing_type_counts(
    *,
    total_listings: int,
    sale_sample_count: int,
    rent_sample_count: int,
    sample_count: int,
) -> tuple[int, int]:
    if total_listings <= 0 or sample_count <= 0:
        return 0, 0
    sale_count = int(round(total_listings * sale_sample_count / sample_count))
    sale_count = min(max(sale_count, 0), total_listings)
    rent_count = max(total_listings - sale_count, 0)
    if rent_sample_count and not sale_sample_count:
        rent_count = min(total_listings, int(round(total_listings * rent_sample_count / sample_count)))
        sale_count = max(total_listings - rent_count, 0)
    return sale_count, rent_count


@router.get("/stats")
async def get_market_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get overall market statistics."""
    cached = _cached_market_stats()
    if cached is not None:
        return cached

    total_q = await db.execute(
        text("SELECT reltuples::bigint FROM pg_class WHERE oid = 'listings'::regclass")
    )
    total_listings = _positive_int(total_q.scalar_one())

    distinct_q = await db.execute(
        text(
            """
            SELECT attname, n_distinct
            FROM pg_stats
            WHERE schemaname = 'public'
              AND tablename = 'listings'
              AND attname IN ('city', 'district')
            """
        )
    )
    distinct_counts = {
        str(attname): _estimate_distinct_count(
            total_listings=total_listings,
            n_distinct=n_distinct,
        )
        for attname, n_distinct in distinct_q.all()
    }

    sample_q = await db.execute(
        text(
            """
            SELECT
                avg(price) FILTER (WHERE price BETWEEN 0.01 AND 1000) AS avg_price,
                avg(area) FILTER (WHERE area BETWEEN 1 AND 10000) AS avg_area,
                count(*) FILTER (WHERE listing_type = 'sale') AS sale_sample_count,
                count(*) FILTER (WHERE listing_type = 'rent') AS rent_sample_count,
                count(*) AS sample_count
            FROM listings TABLESAMPLE SYSTEM (1)
            WHERE is_active = true
            """
        )
    )
    avg_price, avg_area, sale_sample_count, rent_sample_count, sample_count = sample_q.one()
    sale_count, rent_count = _estimate_listing_type_counts(
        total_listings=total_listings,
        sale_sample_count=_positive_int(sale_sample_count),
        rent_sample_count=_positive_int(rent_sample_count),
        sample_count=_positive_int(sample_count),
    )

    return _store_market_stats({
        "total_listings": total_listings,
        "average_price_billion": round(avg_price, 2) if avg_price else None,
        "average_area_m2": round(avg_area, 1) if avg_area else None,
        "listings_for_sale": sale_count or 0,
        "listings_for_rent": rent_count or 0,
        "total_cities": distinct_counts.get("city", 0),
        "total_districts": distinct_counts.get("district", 0),
    })


@router.get("/top-locations")
async def get_top_locations(
    listing_type: str | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get locations with the most listings."""
    cache_key = ("top_locations", listing_type or "", limit)
    cached = _cached_market_query(cache_key)
    if cached is not None:
        return cached

    query = (
        select(Listing.city, Listing.district, func.count().label("count"))
        .where(Listing.is_active == True, Listing.district.isnot(None))
    )
    if listing_type:
        query = query.where(Listing.listing_type == listing_type)

    query = query.group_by(Listing.city, Listing.district).order_by(func.count().desc()).limit(limit)
    result = await db.execute(query)

    return _store_market_query(cache_key, {
        "items": [
            {"city": row.city, "district": row.district, "count": row.count}
            for row in result.all()
        ]
    })


@router.get("/price-by-district")
async def get_price_by_district(
    city: str | None = None,
    listing_type: str = "sale",
    db: AsyncSession = Depends(get_db),
):
    """Get average price statistics grouped by district."""
    cache_key = ("price_by_district", city or "", listing_type)
    cached = _cached_market_query(cache_key)
    if cached is not None:
        return cached

    query = (
        select(
            Listing.city,
            Listing.district,
            func.count().label("count"),
            func.avg(Listing.price).label("avg_price"),
            func.min(Listing.price).label("min_price"),
            func.max(Listing.price).label("max_price"),
            func.avg(Listing.price_per_m2).label("avg_price_per_m2"),
        )
        .where(
            Listing.is_active == True,
            Listing.listing_type == listing_type,
            Listing.price.isnot(None),
            Listing.district.isnot(None),
        )
    )
    if city:
        query = query.where(Listing.city.ilike(f"%{city}%"))

    query = query.group_by(Listing.city, Listing.district).order_by(func.avg(Listing.price).desc())
    result = await db.execute(query)

    return _store_market_query(cache_key, {
        "items": [
            {
                "city": row.city,
                "district": row.district,
                "count": row.count,
                "avg_price": round(row.avg_price, 2) if row.avg_price else None,
                "min_price": round(row.min_price, 2) if row.min_price else None,
                "max_price": round(row.max_price, 2) if row.max_price else None,
                "avg_price_per_m2": round(row.avg_price_per_m2, 2) if row.avg_price_per_m2 else None,
            }
            for row in result.all()
        ]
    })


@router.get("/property-types")
async def get_property_type_stats(
    listing_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get listing count grouped by property type."""
    cache_key = ("property_types", listing_type or "")
    cached = _cached_market_query(cache_key)
    if cached is not None:
        return cached

    query = (
        select(Listing.property_type, func.count().label("count"))
        .where(Listing.is_active == True, Listing.property_type.isnot(None))
    )
    if listing_type:
        query = query.where(Listing.listing_type == listing_type)

    query = query.group_by(Listing.property_type).order_by(func.count().desc())
    result = await db.execute(query)

    return _store_market_query(cache_key, {
        "items": [
            {"property_type": row.property_type, "count": row.count}
            for row in result.all()
        ]
    })


@router.get("/categories")
async def get_categories(
    db: AsyncSession = Depends(get_db),
):
    """Get all unique categories/property types."""
    cache_key = ("categories",)
    cached = _cached_market_query(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        select(Listing.property_type)
        .where(Listing.is_active == True, Listing.property_type.isnot(None))
        .distinct()
        .order_by(Listing.property_type)
    )
    return _store_market_query(cache_key, {"items": [row[0] for row in result.all()]})


@router.get("/cities")
async def get_cities(
    db: AsyncSession = Depends(get_db),
):
    """Get all unique cities with listing counts."""
    cache_key = ("cities",)
    cached = _cached_market_query(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        select(Listing.city, func.count().label("count"))
        .where(Listing.is_active == True, Listing.city.isnot(None))
        .group_by(Listing.city)
        .order_by(func.count().desc())
    )
    return _store_market_query(
        cache_key,
        {"items": [{"name": row.city, "count": row.count} for row in result.all()]},
    )


@router.get("/districts")
async def get_districts(
    city: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get districts, optionally filtered by city."""
    cache_key = ("districts", city or "")
    cached = _cached_market_query(cache_key)
    if cached is not None:
        return cached

    query = (
        select(Listing.district, Listing.city, func.count().label("count"))
        .where(Listing.is_active == True, Listing.district.isnot(None))
    )
    if city:
        query = query.where(Listing.city.ilike(f"%{city}%"))

    query = query.group_by(Listing.district, Listing.city).order_by(func.count().desc())
    result = await db.execute(query)

    return _store_market_query(cache_key, {
        "items": [
            {"district": row.district, "city": row.city, "count": row.count}
            for row in result.all()
        ]
    })
