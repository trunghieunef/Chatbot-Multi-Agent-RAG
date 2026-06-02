from pathlib import Path

from pgvector.sqlalchemy import Vector

from app.models import Chunk, Project


def test_chunk_embedding_dimension_is_1024():
    embedding_type = Chunk.__table__.columns["embedding"].type

    assert isinstance(embedding_type, Vector)
    assert embedding_type.dim == 1024


def test_project_model_no_longer_has_legacy_embedding_column():
    assert "embedding" not in Project.__table__.columns


def test_bge_m3_migration_rebuilds_chunks_vector_index():
    migration = Path("backend/alembic/versions/20260801_0007_bge_m3_embeddings.py")

    body = migration.read_text(encoding="utf-8")

    assert "DELETE FROM chunks" in body
    assert "vector(1024)" in body
    assert "DROP INDEX IF EXISTS ix_chunks_embedding_hnsw" in body
    assert "CREATE INDEX ix_chunks_embedding_hnsw" in body
    assert "ALTER TABLE projects DROP COLUMN IF EXISTS embedding" in body
