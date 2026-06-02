"""
SQLAlchemy ORM models for real estate projects.
"""

from sqlalchemy import (
    Column, DateTime, Float, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import ARRAY

from app.database import Base


class Project(Base):
    """A real estate development project."""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    slug = Column(String(255), unique=True, index=True)

    # Developer
    developer = Column(String(200))

    # Location
    location = Column(Text)         # Full address
    district = Column(String(100))
    city = Column(String(100))
    latitude = Column(Float)
    longitude = Column(Float)

    # Project info
    total_units = Column(Integer)
    price_range = Column(String(200))  # "2.5 - 4.8 tỷ"
    area_range = Column(String(200))   # "55 - 120 m²"
    status = Column(String(50))        # 'upcoming', 'selling', 'completed'
    project_type = Column(String(80))  # 'apartment', 'townhouse', 'villa', ...

    # Details
    description = Column(Text)
    amenities = Column(ARRAY(String))  # ['Hồ bơi', 'Gym', 'Công viên', ...]

    # Meta
    url = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Project(id={self.id}, name='{self.name}')>"
