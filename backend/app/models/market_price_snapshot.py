from sqlalchemy import Column, Date, DateTime, Float, Index, Integer, String, UniqueConstraint, func

from app.database import Base


class MarketPriceSnapshot(Base):
    """Aggregated market price snapshot for location/property/month segments."""

    __tablename__ = "market_price_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    city = Column(String(100), nullable=False)
    district = Column(String(100), nullable=False)
    ward = Column(String(100), nullable=False, default="")
    street = Column(String(150), nullable=False, default="")
    property_type = Column(String(120), nullable=False)
    month = Column(Date, nullable=False)
    period = Column(String(7), nullable=False)
    listing_count = Column(Integer, nullable=False)
    avg_price = Column(Float)
    median_price = Column(Float)
    avg_price_per_m2 = Column(Float)
    median_price_per_m2 = Column(Float)
    p25_price_per_m2 = Column(Float)
    p75_price_per_m2 = Column(Float)
    source = Column(String(150), nullable=False, default="tinixai/vietnam-real-estates")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "city",
            "district",
            "ward",
            "street",
            "property_type",
            "month",
            "source",
            name="uq_market_price_snapshot_segment",
        ),
        Index("ix_market_snapshot_city_district", "city", "district"),
        Index("ix_market_snapshot_property_type", "property_type"),
        Index("ix_market_snapshot_month", "month"),
    )
