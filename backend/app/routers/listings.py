"""
Listings API router.

Endpoints for browsing, searching, and filtering real estate listings.
"""

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.listing import Listing
from app.models.listing_image import ListingImage
from app.schemas.common import PaginatedResponse
from app.schemas.listing import ListingResponse, ListingCardResponse

router = APIRouter(prefix="/listings", tags=["Listings"])


def _apply_filters(query, params: dict):
    """Apply filter conditions to a listing query."""
    filters = []

    if params.get("search"):
        search_term = f"%{params['search']}%"
        filters.append(
            or_(
                Listing.title.ilike(search_term),
                Listing.description.ilike(search_term),
                Listing.address.ilike(search_term),
                Listing.district.ilike(search_term),
                Listing.city.ilike(search_term),
            )
        )

    if params.get("listing_type"):
        filters.append(Listing.listing_type == params["listing_type"])
    if params.get("property_type"):
        filters.append(Listing.property_type == params["property_type"])
    if params.get("city"):
        filters.append(Listing.city.ilike(f"%{params['city']}%"))
    if params.get("district"):
        filters.append(Listing.district.ilike(f"%{params['district']}%"))
    if params.get("min_price") is not None:
        filters.append(Listing.price >= params["min_price"])
    if params.get("max_price") is not None:
        filters.append(Listing.price <= params["max_price"])
    if params.get("min_area") is not None:
        filters.append(Listing.area >= params["min_area"])
    if params.get("max_area") is not None:
        filters.append(Listing.area <= params["max_area"])
    if params.get("bedrooms") is not None:
        filters.append(Listing.bedrooms == params["bedrooms"])
    if params.get("bathrooms") is not None:
        filters.append(Listing.bathrooms == params["bathrooms"])
    if params.get("direction"):
        filters.append(Listing.direction.ilike(f"%{params['direction']}%"))

    if filters:
        query = query.where(and_(*filters))

    return query


def _apply_sort(query, sort: str | None):
    """Apply sorting to a listing query."""
    sort_map = {
        "price_asc": Listing.price.asc().nullslast(),
        "price_desc": Listing.price.desc().nullslast(),
        "area_asc": Listing.area.asc().nullslast(),
        "area_desc": Listing.area.desc().nullslast(),
        "newest": Listing.created_at.desc(),
    }
    order = sort_map.get(sort, Listing.created_at.desc())
    return query.order_by(order)


def listing_card_response(listing: Listing, image_urls: list[str] | None = None) -> ListingCardResponse:
    response = ListingCardResponse.model_validate(listing)
    urls = image_urls or []
    response.image_urls = urls
    response.primary_image_url = urls[0] if urls else None
    return response


def listing_detail_response(listing: Listing, image_urls: list[str] | None = None) -> ListingResponse:
    response = ListingResponse.model_validate(listing)
    urls = image_urls or []
    response.image_urls = urls
    response.primary_image_url = urls[0] if urls else None
    return response


async def _listing_image_map(db: AsyncSession, listing_ids: list[int]) -> dict[int, list[str]]:
    if not listing_ids:
        return {}
    result = await db.execute(
        select(ListingImage)
        .where(ListingImage.listing_id.in_(listing_ids))
        .order_by(ListingImage.listing_id, ListingImage.sort_order, ListingImage.id)
    )
    images_by_listing: dict[int, list[str]] = {listing_id: [] for listing_id in listing_ids}
    for image in result.scalars().all():
        images_by_listing.setdefault(image.listing_id, []).append(image.image_url)
    return images_by_listing


@router.get("", response_model=PaginatedResponse)
async def get_listings(
    search: str | None = None,
    listing_type: str | None = None,
    property_type: str | None = None,
    city: str | None = None,
    district: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_area: float | None = None,
    max_area: float | None = None,
    bedrooms: int | None = None,
    bathrooms: int | None = None,
    direction: str | None = None,
    sort: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated listings with filters."""
    params = {
        "search": search, "listing_type": listing_type,
        "property_type": property_type, "city": city, "district": district,
        "min_price": min_price, "max_price": max_price,
        "min_area": min_area, "max_area": max_area,
        "bedrooms": bedrooms, "bathrooms": bathrooms, "direction": direction,
    }

    # Count total
    count_query = select(func.count()).select_from(Listing).where(Listing.is_active == True)
    count_query = _apply_filters(count_query, params)
    total = (await db.execute(count_query)).scalar() or 0

    # Fetch page
    query = select(Listing).where(Listing.is_active == True)
    query = _apply_filters(query, params)
    query = _apply_sort(query, sort)
    query = query.offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    listings = result.scalars().all()
    image_map = await _listing_image_map(db, [listing.id for listing in listings])

    return PaginatedResponse(
        items=[listing_card_response(l, image_map.get(l.id, [])) for l in listings],
        total=total,
        page=page,
        limit=limit,
        total_pages=math.ceil(total / limit) if total > 0 else 0,
    )


@router.get("/by-product-id/{product_id}", response_model=ListingResponse)
async def get_listing_by_product_id(
    product_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single listing by its original product_id."""
    result = await db.execute(
        select(Listing).where(Listing.product_id == product_id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    image_map = await _listing_image_map(db, [listing.id])
    return listing_detail_response(listing, image_map.get(listing.id, []))


@router.get("/similar/{listing_id}", response_model=list[ListingCardResponse])
async def get_similar_listings(
    listing_id: int,
    limit: int = Query(default=6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Get similar listings based on same district, property type, and price range."""
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    # Simple similarity: same district + property type + similar price range
    filters = [
        Listing.id != listing_id,
        Listing.is_active == True,
    ]
    if listing.district:
        filters.append(Listing.district == listing.district)
    if listing.property_type:
        filters.append(Listing.property_type == listing.property_type)
    if listing.price:
        price_margin = listing.price * 0.3  # ±30%
        filters.append(Listing.price.between(listing.price - price_margin, listing.price + price_margin))

    query = select(Listing).where(and_(*filters)).limit(limit)
    result = await db.execute(query)
    similar = result.scalars().all()
    image_map = await _listing_image_map(db, [item.id for item in similar])

    return [listing_card_response(l, image_map.get(l.id, [])) for l in similar]


@router.get("/{listing_id}", response_model=ListingResponse)
async def get_listing_detail(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a single listing by ID."""
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    image_map = await _listing_image_map(db, [listing.id])
    return listing_detail_response(listing, image_map.get(listing.id, []))
