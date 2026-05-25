from sqlalchemy import Column, DateTime, Index, Integer, String, Text, func
from pgvector.sqlalchemy import Vector

from app.database import Base


class Chunk(Base):
    """Semantic retrieval chunk linked to a listing, project, or article."""

    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_type = Column(String(30), nullable=False)
    parent_id = Column(Integer, nullable=False)
    chunk_type = Column(String(50), nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=False)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_chunks_parent", "parent_type", "parent_id"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
