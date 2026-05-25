"""
Pydantic schemas for Listing endpoints.
"""

from datetime import datetime
from pydantic import BaseModel, Field


# ─── Response schemas ──────────────────────────────────────────

class ListingResponse(BaseModel):
    """Full listing detail response."""
    id: int
    product_id: str
    listing_type: str | None = None
    property_type: str | None = None
    title: str | None = None
    description: str | None = None

    # Pricing
    price: float | None = None
    price_unit: str | None = None
    price_text: str | None = None
    price_per_m2: float | None = None
    price_per_m2_text: str | None = None

    # Specs
    area: float | None = None
    area_text: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    floors: int | None = None
    direction: str | None = None
    balcony_direction: str | None = None
    frontage: str | None = None
    road_width: str | None = None

    # Status
    legal_status: str | None = None
    furniture: str | None = None

    # Location
    address: str | None = None
    ward: str | None = None
    district: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    # Contact
    contact_name: str | None = None
    contact_phone: str | None = None

    # Dates
    post_date: str | None = None
    expiry_date: str | None = None

    # Meta
    url: str | None = None
    badge: str | None = None

    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ListingCardResponse(BaseModel):
    """Condensed listing for grid/card views."""
    id: int
    product_id: str
    listing_type: str | None = None
    property_type: str | None = None
    title: str | None = None
    price_text: str | None = None
    price_per_m2_text: str | None = None
    area_text: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    district: str | None = None
    city: str | None = None
    address: str | None = None
    contact_name: str | None = None
    post_date: str | None = None
    badge: str | None = None
    url: str | None = None

    class Config:
        from_attributes = True


# ─── Filter / query schema ────────────────────────────────────

class ListingFilterParams(BaseModel):
    """Query parameters for filtering listings."""
    search: str | None = None
    listing_type: str | None = Field(default=None, description="sale | rent")
    property_type: str | None = None
    city: str | None = None
    district: str | None = None
    min_price: float | None = Field(default=None, description="Min price (billion VND)")
    max_price: float | None = Field(default=None, description="Max price (billion VND)")
    min_area: float | None = None
    max_area: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    direction: str | None = None
    sort: str | None = Field(default=None, description="price_asc | price_desc | newest | area_asc | area_desc")
