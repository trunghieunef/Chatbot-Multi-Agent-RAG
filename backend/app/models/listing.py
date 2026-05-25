"""
SQLAlchemy ORM models for listings (sale + rent).
"""

import datetime
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, Float, Index, Integer,
    String, Text, func,
)

from app.database import Base


class Listing(Base):
    """A real estate listing (sale or rent)."""

    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(50), unique=True, nullable=False, index=True)

    # Classification
    listing_type = Column(String(20), nullable=False, default="sale")  # 'sale' | 'rent'
    property_type = Column(String(80))   # 'apartment', 'house', 'land', 'shophouse', ...

    # Core info
    title = Column(Text)
    description = Column(Text)

    # Pricing
    price = Column(Float)                # Numeric price value
    price_unit = Column(String(30))      # 'billion', 'million', 'million/month'
    price_text = Column(String(100))     # Raw text: "4,68 tỷ"
    price_per_m2 = Column(Float)
    price_per_m2_text = Column(String(100))

    # Specs
    area = Column(Float)                 # m²
    area_text = Column(String(50))
    bedrooms = Column(Integer)
    bathrooms = Column(Integer)
    floors = Column(Integer)
    direction = Column(String(30))       # Hướng nhà
    balcony_direction = Column(String(30))
    frontage = Column(String(50))        # Mặt tiền
    road_width = Column(String(50))      # Đường vào

    # Status
    legal_status = Column(String(80))    # Pháp lý
    furniture = Column(String(80))       # Nội thất

    # Location
    address = Column(Text)
    ward = Column(String(100))           # Phường/Xã
    district = Column(String(100))       # Quận/Huyện
    city = Column(String(100))           # Tỉnh/Thành phố
    latitude = Column(Float)
    longitude = Column(Float)

    # Contact
    contact_name = Column(String(150))
    contact_phone = Column(String(30))

    # Dates
    post_date = Column(String(50))
    expiry_date = Column(String(50))

    # Meta
    url = Column(Text)
    badge = Column(String(50))
    listing_type_label = Column(String(50))  # Loại tin (Tin VIP, Tin thường, ...)
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Indexes for common queries
    __table_args__ = (
        Index("idx_listing_type", "listing_type"),
        Index("idx_city", "city"),
        Index("idx_district", "district"),
        Index("idx_property_type", "property_type"),
        Index("idx_price", "price"),
        Index("idx_area", "area"),
        Index("idx_bedrooms", "bedrooms"),
        Index("idx_post_date", "post_date"),
        Index("idx_is_active", "is_active"),
    )

    def __repr__(self):
        return f"<Listing(id={self.id}, product_id='{self.product_id}', title='{self.title[:40] if self.title else ''}...')>"
