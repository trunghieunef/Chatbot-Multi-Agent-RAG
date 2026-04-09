"""
Market data and analytics API router.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.listing import Listing

router = APIRouter(prefix="/market", tags=["Market Data"])


@router.get("/stats")
async def get_market_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get overall market statistics."""
    # Total listings
    total_q = await db.execute(
        select(func.count()).select_from(Listing).where(Listing.is_active == True)
    )
    total_listings = total_q.scalar() or 0

    # Average price
    avg_price_q = await db.execute(
        select(func.avg(Listing.price)).where(
            Listing.is_active == True,
            Listing.price.isnot(None),
        )
    )
    avg_price = avg_price_q.scalar()

    # Average area
    avg_area_q = await db.execute(
        select(func.avg(Listing.area)).where(
            Listing.is_active == True,
            Listing.area.isnot(None),
        )
    )
    avg_area = avg_area_q.scalar()

    # Count by listing type
    type_counts_q = await db.execute(
        select(Listing.listing_type, func.count())
        .where(Listing.is_active == True)
        .group_by(Listing.listing_type)
    )
    type_counts = {row[0]: row[1] for row in type_counts_q.all()}

    # Unique cities and districts
    cities_q = await db.execute(
        select(func.count(func.distinct(Listing.city))).where(Listing.is_active == True)
    )
    total_cities = cities_q.scalar() or 0

    districts_q = await db.execute(
        select(func.count(func.distinct(Listing.district))).where(Listing.is_active == True)
    )
    total_districts = districts_q.scalar() or 0

    return {
        "total_listings": total_listings,
        "average_price_billion": round(avg_price, 2) if avg_price else None,
        "average_area_m2": round(avg_area, 1) if avg_area else None,
        "listings_for_sale": type_counts.get("sale", 0),
        "listings_for_rent": type_counts.get("rent", 0),
        "total_cities": total_cities,
        "total_districts": total_districts,
    }


@router.get("/top-locations")
async def get_top_locations(
    listing_type: str | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get locations with the most listings."""
    query = (
        select(Listing.city, Listing.district, func.count().label("count"))
        .where(Listing.is_active == True, Listing.district.isnot(None))
    )
    if listing_type:
        query = query.where(Listing.listing_type == listing_type)

    query = query.group_by(Listing.city, Listing.district).order_by(func.count().desc()).limit(limit)
    result = await db.execute(query)

    return {
        "items": [
            {"city": row.city, "district": row.district, "count": row.count}
            for row in result.all()
        ]
    }


@router.get("/price-by-district")
async def get_price_by_district(
    city: str | None = None,
    listing_type: str = "sale",
    db: AsyncSession = Depends(get_db),
):
    """Get average price statistics grouped by district."""
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

    return {
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
    }


@router.get("/property-types")
async def get_property_type_stats(
    listing_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get listing count grouped by property type."""
    query = (
        select(Listing.property_type, func.count().label("count"))
        .where(Listing.is_active == True, Listing.property_type.isnot(None))
    )
    if listing_type:
        query = query.where(Listing.listing_type == listing_type)

    query = query.group_by(Listing.property_type).order_by(func.count().desc())
    result = await db.execute(query)

    return {
        "items": [
            {"property_type": row.property_type, "count": row.count}
            for row in result.all()
        ]
    }


@router.get("/categories")
async def get_categories(
    db: AsyncSession = Depends(get_db),
):
    """Get all unique categories/property types."""
    result = await db.execute(
        select(Listing.property_type)
        .where(Listing.is_active == True, Listing.property_type.isnot(None))
        .distinct()
        .order_by(Listing.property_type)
    )
    return {"items": [row[0] for row in result.all()]}


@router.get("/cities")
async def get_cities(
    db: AsyncSession = Depends(get_db),
):
    """Get all unique cities with listing counts."""
    result = await db.execute(
        select(Listing.city, func.count().label("count"))
        .where(Listing.is_active == True, Listing.city.isnot(None))
        .group_by(Listing.city)
        .order_by(func.count().desc())
    )
    return {"items": [{"name": row.city, "count": row.count} for row in result.all()]}


@router.get("/districts")
async def get_districts(
    city: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get districts, optionally filtered by city."""
    query = (
        select(Listing.district, Listing.city, func.count().label("count"))
        .where(Listing.is_active == True, Listing.district.isnot(None))
    )
    if city:
        query = query.where(Listing.city.ilike(f"%{city}%"))

    query = query.group_by(Listing.district, Listing.city).order_by(func.count().desc())
    result = await db.execute(query)

    return {
        "items": [
            {"district": row.district, "city": row.city, "count": row.count}
            for row in result.all()
        ]
    }
