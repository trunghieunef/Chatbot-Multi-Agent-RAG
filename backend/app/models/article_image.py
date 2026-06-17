"""SQLAlchemy ORM model for article image URLs."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, func

from app.database import Base


class ArticleImage(Base):
    """An image URL associated with an article."""

    __tablename__ = "article_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
    article_url = Column(Text, nullable=True, index=True)
    image_url = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_primary = Column(Boolean, nullable=False, default=False)
    source = Column(String(80), nullable=False, default="batdongsan")
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_article_images_article_order", "article_id", "sort_order"),
        Index("ix_article_images_url_order", "article_url", "sort_order"),
    )
