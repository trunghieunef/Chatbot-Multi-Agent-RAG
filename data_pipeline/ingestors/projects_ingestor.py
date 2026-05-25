from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings
from app.database import async_session, engine
from app.models import Chunk, Project
from data_pipeline.clean import row_to_project
from data_pipeline.embed import GeminiEmbedder


def build_project_chunks(project: dict) -> list[dict[str, Any]]:
    """Build semantic chunks for a project: overview, description, amenities."""
    chunks: list[dict[str, Any]] = []

    overview_parts: list[str] = []
    if project.get("name"):
        overview_parts.append(project["name"])
    if project.get("developer"):
        overview_parts.append(f"Chủ đầu tư: {project['developer']}")
    region = ", ".join(part for part in (project.get("district"), project.get("city")) if part)
    if region:
        overview_parts.append(f"Khu vực: {region}")
    if project.get("status"):
        overview_parts.append(f"Trạng thái: {project['status']}")
    if project.get("price_range"):
        overview_parts.append(f"Giá: {project['price_range']}")
    if project.get("area_range"):
        overview_parts.append(f"Diện tích: {project['area_range']}")

    overview = ". ".join(overview_parts)
    if overview:
        chunks.append({"chunk_type": "overview", "text": overview})

    description = (project.get("description") or "").strip()
    if description:
        chunks.append({"chunk_type": "description", "text": description})

    amenities = project.get("amenities") or []
    if amenities:
        chunks.append({"chunk_type": "amenities", "text": "Tiện ích: " + ", ".join(amenities)})

    return chunks


async def upsert_project(session, project_data: dict[str, Any]) -> Project:
    slug = project_data["slug"]
    result = await session.execute(select(Project).where(Project.slug == slug))
    project = result.scalar_one_or_none()
    if project is None:
        project = Project(**project_data)
        session.add(project)
        await session.flush()
        return project
    for key, value in project_data.items():
        setattr(project, key, value)
    await session.flush()
    return project


async def ingest_project_rows(rows: list[dict[str, str]], batch_size: int = 25) -> dict[str, int]:
    settings = get_settings()
    embedder = GeminiEmbedder(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_EMBEDDING_MODEL,
        batch_size=100,
    )

    # pgvector is infrastructure (not schema). Schema lives in Alembic migrations.
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    inserted = 0
    chunks_inserted = 0
    errors = 0

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]

        # Phase 1: clean + chunk in memory.
        prepared: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        for row in batch:
            try:
                project_data = row_to_project(row)
                if not project_data.get("slug"):
                    continue
                chunks = build_project_chunks(project_data)
                prepared.append((project_data, chunks))
            except Exception as exc:
                errors += 1
                print(
                    f"[projects-ingest] clean/chunk failed for {row.get('slug', '?')}: {exc}",
                    file=sys.stderr,
                )

        if not prepared:
            continue

        # Phase 2: one embed call per batch instead of one per project.
        flat_texts = [chunk["text"] for _, chunks in prepared for chunk in chunks]
        try:
            flat_vectors = await embedder.embed_texts(flat_texts)
        except Exception as exc:
            errors += len(prepared)
            print(f"[projects-ingest] embed batch failed: {exc}", file=sys.stderr)
            continue

        cursor = 0
        with_vectors: list[tuple[dict[str, Any], list[dict[str, Any]], list[list[float]]]] = []
        for project_data, chunks in prepared:
            count = len(chunks)
            with_vectors.append((project_data, chunks, flat_vectors[cursor : cursor + count]))
            cursor += count

        # Phase 3: persist within a single session per batch.
        async with async_session() as session:
            for project_data, chunks, vectors in with_vectors:
                try:
                    project = await upsert_project(session, project_data)
                    await session.execute(
                        delete(Chunk).where(
                            Chunk.parent_type == "project",
                            Chunk.parent_id == project.id,
                        )
                    )
                    session.add_all(
                        [
                            Chunk(
                                parent_type="project",
                                parent_id=project.id,
                                chunk_type=chunk["chunk_type"],
                                text=chunk["text"],
                                embedding=vector,
                            )
                            for chunk, vector in zip(chunks, vectors, strict=True)
                        ]
                    )
                    inserted += 1
                    chunks_inserted += len(chunks)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    errors += 1
                    print(
                        f"[projects-ingest] db write failed for {project_data.get('slug', '?')}: {exc}",
                        file=sys.stderr,
                    )
            await session.commit()

    return {"projects": inserted, "chunks": chunks_inserted, "errors": errors}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest project CSV into PostgreSQL chunks")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--batch-size", type=int, default=25)
    args = parser.parse_args()
    with open(args.csv, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    print(await ingest_project_rows(rows, batch_size=args.batch_size))


if __name__ == "__main__":
    asyncio.run(main())
