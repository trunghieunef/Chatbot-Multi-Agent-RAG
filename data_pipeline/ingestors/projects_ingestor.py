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
from data_pipeline.embed import BGEEmbedder


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


def empty_ingest_result() -> dict[str, int]:
    return {
        "published": 0,
        "indexed": 0,
        "chunks": 0,
        "publish_errors": 0,
        "index_errors": 0,
    }


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


async def publish_project_batch(projects_data: list[dict[str, Any]]) -> list[Project]:
    persisted: list[Project] = []
    async with async_session() as session:
        for project_data in projects_data:
            project = await upsert_project(session, project_data)
            persisted.append(project)
        await session.commit()
    return persisted


async def index_project_batch(
    projects_with_chunks: list[tuple[Project, list[dict[str, Any]]]],
    *,
    embedder: Any,
) -> dict[str, int]:
    if not projects_with_chunks:
        return {"indexed": 0, "chunks": 0, "index_errors": 0}

    flat_texts = [
        chunk["text"]
        for _, chunks in projects_with_chunks
        for chunk in chunks
    ]
    if not flat_texts:
        return {"indexed": 0, "chunks": 0, "index_errors": 0}

    try:
        flat_vectors = await embedder.embed_texts(flat_texts)
    except Exception as exc:
        print(f"[projects-ingest] semantic index embed batch failed: {exc}", file=sys.stderr)
        return {
            "indexed": 0,
            "chunks": 0,
            "index_errors": len(projects_with_chunks),
        }

    cursor = 0
    indexed = 0
    chunks_inserted = 0
    index_errors = 0

    async with async_session() as session:
        for project, chunks in projects_with_chunks:
            count = len(chunks)
            vectors = flat_vectors[cursor : cursor + count]
            cursor += count
            try:
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
                indexed += 1
                chunks_inserted += len(chunks)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                index_errors += 1
                print(
                    f"[projects-ingest] semantic index db write failed for {project.slug}: {exc}",
                    file=sys.stderr,
                )
        await session.commit()

    return {"indexed": indexed, "chunks": chunks_inserted, "index_errors": index_errors}


async def ensure_vector_extension() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


async def ingest_project_rows(rows: list[dict[str, str]], batch_size: int = 25) -> dict[str, int]:
    settings = get_settings()
    embedder = BGEEmbedder(
        model_name=settings.HF_EMBEDDING_MODEL,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
        embedding_dim=settings.EMBEDDING_DIM,
        device=settings.HF_EMBEDDING_DEVICE or None,
    )

    # pgvector is infrastructure (not schema). Schema lives in Alembic migrations.
    await ensure_vector_extension()
    result = empty_ingest_result()

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]

        # Phase 1: clean structured project data.
        prepared: list[dict[str, Any]] = []
        for row in batch:
            try:
                project_data = row_to_project(row)
                if not project_data.get("slug"):
                    continue
                prepared.append(project_data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                result["publish_errors"] += 1
                print(
                    f"[projects-ingest] clean failed for {row.get('slug', '?')}: {exc}",
                    file=sys.stderr,
                )

        if not prepared:
            continue

        try:
            persisted = await publish_project_batch(prepared)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result["publish_errors"] += len(prepared)
            print(f"[projects-ingest] publish batch failed: {exc}", file=sys.stderr)
            continue

        result["published"] += len(persisted)

        projects_with_chunks: list[tuple[Project, list[dict[str, Any]]]] = []
        for project, project_data in zip(persisted, prepared, strict=True):
            try:
                chunks = build_project_chunks(project_data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                result["index_errors"] += 1
                print(
                    f"[projects-ingest] semantic index chunk build failed for {project.slug}: {exc}",
                    file=sys.stderr,
                )
                continue
            projects_with_chunks.append((project, chunks))

        index_result = await index_project_batch(projects_with_chunks, embedder=embedder)
        result["indexed"] += index_result["indexed"]
        result["chunks"] += index_result["chunks"]
        result["index_errors"] += index_result["index_errors"]

    return result


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
