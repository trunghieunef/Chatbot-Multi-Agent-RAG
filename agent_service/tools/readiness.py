from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from app.database import async_session
from app.models import Article, Chunk, Listing, Project


def _status(parent_count: int, chunk_count: int) -> str:
    return "ready" if parent_count > 0 and chunk_count > 0 else "not_ready"


async def count_source(source_name: str) -> dict[str, Any]:
    async with async_session() as session:
        if source_name == "listings":
            parent_result = await session.execute(select(func.count(Listing.id)))
            chunk_result = await session.execute(
                select(func.count(Chunk.id)).where(Chunk.parent_type == "listing")
            )
        elif source_name == "projects":
            parent_result = await session.execute(select(func.count(Project.id)))
            chunk_result = await session.execute(
                select(func.count(Chunk.id)).where(Chunk.parent_type == "project")
            )
        elif source_name == "news":
            parent_result = await session.execute(
                select(func.count(Article.id)).where(Article.category != "legal")
            )
            chunk_result = await session.execute(
                select(func.count(Chunk.id))
                .select_from(Chunk)
                .join(Article, Chunk.parent_id == Article.id)
                .where(Chunk.parent_type == "article", Article.category != "legal")
            )
        elif source_name == "legal":
            parent_result = await session.execute(
                select(func.count(Article.id)).where(Article.category == "legal")
            )
            chunk_result = await session.execute(
                select(func.count(Chunk.id))
                .select_from(Chunk)
                .join(Article, Chunk.parent_id == Article.id)
                .where(Chunk.parent_type == "article", Article.category == "legal")
            )
        else:
            return {
                "status": "not_ready",
                "parent_count": 0,
                "chunk_count": 0,
            }

        parent_count = int(parent_result.scalar_one())
        chunk_count = int(chunk_result.scalar_one())
        return {
            "status": _status(parent_count, chunk_count),
            "parent_count": parent_count,
            "chunk_count": chunk_count,
        }


async def build_readiness_snapshot() -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for source_name in ("listings", "projects", "news", "legal"):
        try:
            snapshot[source_name] = await count_source(source_name)
        except Exception as exc:
            snapshot[source_name] = {
                "status": "unknown",
                "parent_count": 0,
                "chunk_count": 0,
                "warning": str(exc),
            }
    return snapshot
