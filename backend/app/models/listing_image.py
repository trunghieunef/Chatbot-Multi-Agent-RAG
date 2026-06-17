"""SQLAlchemy ORM model for listing image URLs."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, func

from app.database import Base


class ListingImage(Base):
    """An image URL associated with a listing."""

    __tablename__ = "listing_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    listing_id = Column(Integer, ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(50), nullable=False, index=True)
    image_url = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_primary = Column(Boolean, nullable=False, default=False)
    source = Column(String(80), nullable=False, default="batdongsan")
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_listing_images_listing_order", "listing_id", "sort_order"),
        Index("ix_listing_images_product_order", "product_id", "sort_order"),
    )
