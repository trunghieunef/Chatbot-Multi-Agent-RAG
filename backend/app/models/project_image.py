"""SQLAlchemy ORM model for project image URLs."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, func

from app.database import Base


class ProjectImage(Base):
    """An image URL associated with a project."""

    __tablename__ = "project_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    project_slug = Column(String(255), nullable=True, index=True)
    image_url = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_primary = Column(Boolean, nullable=False, default=False)
    source = Column(String(80), nullable=False, default="batdongsan")
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_project_images_project_order", "project_id", "sort_order"),
        Index("ix_project_images_slug_order", "project_slug", "sort_order"),
    )
