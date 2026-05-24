from sqlalchemy import Column, Date, DateTime, Integer, String, Text, func

from app.database import Base


class Article(Base):
    """A crawled article or legal knowledge base document."""

    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    category = Column(String(50), index=True)
    source = Column(String(150))
    post_date = Column(Date)
    url = Column(Text, unique=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
