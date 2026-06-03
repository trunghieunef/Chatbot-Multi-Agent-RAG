from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class SourceReadiness(Base):
    __tablename__ = "source_readiness"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(80), nullable=False, unique=True, index=True)
    status = Column(String(30), nullable=False, default="unknown")
    parent_count = Column(Integer, nullable=False, default=0)
    chunk_count = Column(Integer, nullable=False, default=0)
    last_indexed_at = Column(DateTime, nullable=True)
    details_json = Column(JSONB, nullable=False, default={})
    warning = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
