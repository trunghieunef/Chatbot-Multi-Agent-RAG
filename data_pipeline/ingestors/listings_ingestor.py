from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings
from app.database import Base, async_session, engine
from app.models import Chunk, Listing
from data_pipeline.chunk import build_listing_chunks
from data_pipeline.clean import row_to_listing
from data_pipeline.embed import GeminiEmbedder


def read_csv_rows(csv_path: str) -> list[dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def prepare_listing_chunks(
    listing_id: int,
    listing_data: dict[str, Any],
    vectors: list[list[float]],
) -> list[dict[str, Any]]:
    chunks = build_listing_chunks(listing_data)
    if len(chunks) != len(vectors):
        raise ValueError("chunk/vector count mismatch")
    return [
        {
            "parent_type": "listing",
            "parent_id": listing_id,
            "chunk_type": chunk["chunk_type"],
            "text": chunk["text"],
            "embedding": vector,
        }
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


async def upsert_listing(session, listing_data: dict[str, Any]) -> Listing:
    product_id = listing_data["product_id"]
    result = await session.execute(select(Listing).where(Listing.product_id == product_id))
    listing = result.scalar_one_or_none()

    if listing is None:
        listing = Listing(**listing_data)
        session.add(listing)
        await session.flush()
        return listing

    for key, value in listing_data.items():
        setattr(listing, key, value)
    await session.flush()
    return listing


async def ingest_listing_rows(rows: list[dict[str, str]], batch_size: int = 50) -> dict[str, int]:
    settings = get_settings()
    embedder = GeminiEmbedder(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_EMBEDDING_MODEL,
        batch_size=100,
    )

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    inserted_or_updated = 0
    chunks_inserted = 0
    errors = 0

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        async with async_session() as session:
            for row in batch:
                try:
                    listing_data = row_to_listing(row)
                    if not listing_data.get("product_id"):
                        continue
                    listing = await upsert_listing(session, listing_data)

                    chunks = build_listing_chunks(listing_data)
                    vectors = await embedder.embed_texts([chunk["text"] for chunk in chunks])
                    chunk_rows = prepare_listing_chunks(listing.id, listing_data, vectors)

                    await session.execute(
                        delete(Chunk).where(
                            Chunk.parent_type == "listing",
                            Chunk.parent_id == listing.id,
                        )
                    )
                    session.add_all([Chunk(**chunk_row) for chunk_row in chunk_rows])
                    inserted_or_updated += 1
                    chunks_inserted += len(chunk_rows)
                except Exception as exc:
                    errors += 1
                    if errors <= 5:
                        print(f"Error on {row.get('product_id', '?')}: {exc}")
            await session.commit()

    return {
        "listings": inserted_or_updated,
        "chunks": chunks_inserted,
        "errors": errors,
    }


async def load_csv_to_db(csv_path: str, batch_size: int = 50) -> dict[str, int]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(csv_path)
    rows = read_csv_rows(csv_path)
    return await ingest_listing_rows(rows, batch_size=batch_size)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest listing CSV into PostgreSQL chunks")
    parser.add_argument("--csv", required=True, help="Path to listing details CSV")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    result = await load_csv_to_db(args.csv, args.batch_size)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
