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
from app.database import async_session, engine
from app.models import Chunk, Listing
from data_pipeline.chunk import build_listing_chunks
from data_pipeline.clean import row_to_listing
from data_pipeline.embed import GeminiEmbedder
from data_pipeline.enrich import GeminiIntentExtractor, NominatimGeocoder


def read_csv_rows(csv_path: str) -> list[dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def prepare_listing_chunks(
    listing_id: int,
    chunks: list[dict[str, Any]],
    vectors: list[list[float]],
) -> list[dict[str, Any]]:
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


async def enrich_listing_data(listing: dict, *, geocoder, intent_extractor) -> dict:
    """Geocode the listing address and attach intent tags.

    Returns a copy of ``listing`` with ``latitude``/``longitude`` populated when
    the address is non-blank and the geocoder resolves it, plus ``intent_tags``
    produced by ``intent_extractor`` from a concatenation of title, description,
    and address.
    """
    enriched = dict(listing)

    address = (enriched.get("address") or "").strip()
    if address:
        coord = await geocoder.geocode(address)
        if coord:
            enriched["latitude"], enriched["longitude"] = coord
        else:
            enriched.setdefault("latitude", None)
            enriched.setdefault("longitude", None)
    else:
        enriched.setdefault("latitude", None)
        enriched.setdefault("longitude", None)

    description_for_intent = " ".join(
        part
        for part in (enriched.get("title"), enriched.get("description"), enriched.get("address"))
        if part
    )
    enriched["intent_tags"] = await intent_extractor.extract(description_for_intent)
    return enriched


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

    geocoder = NominatimGeocoder(
        user_agent=settings.GEOCODER_USER_AGENT,
        rate_limit_seconds=settings.GEOCODER_RATE_LIMIT_SECONDS,
    )
    if settings.INTENT_EXTRACTOR == "gemini" and settings.GEMINI_API_KEY:
        intent_extractor = GeminiIntentExtractor(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_INTENT_MODEL,
        )
    else:
        class _NoOpIntent:
            async def extract(self, _content):
                return []
        intent_extractor = _NoOpIntent()

    # pgvector is infrastructure (not schema). Schema lives in Alembic migrations.
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    inserted_or_updated = 0
    chunks_inserted = 0
    errors = 0

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]

        # Phase 1: clean + enrich + chunk in-memory (geocode + intent network calls).
        prepared: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        for row in batch:
            try:
                listing_data = row_to_listing(row)
                if not listing_data.get("product_id"):
                    continue
                listing_data = await enrich_listing_data(
                    listing_data,
                    geocoder=geocoder,
                    intent_extractor=intent_extractor,
                )
                chunks = build_listing_chunks(listing_data)
                prepared.append((listing_data, chunks))
            except Exception as exc:
                errors += 1
                print(
                    f"[ingest] clean/chunk failed for {row.get('product_id', '?')}: {exc}",
                    file=sys.stderr,
                )

        if not prepared:
            continue

        # Phase 2: one embed call per batch instead of one per listing.
        flat_texts = [chunk["text"] for _, chunks in prepared for chunk in chunks]
        try:
            flat_vectors = await embedder.embed_texts(flat_texts)
        except Exception as exc:
            errors += len(prepared)
            print(f"[ingest] embed batch failed: {exc}", file=sys.stderr)
            continue

        cursor = 0
        with_vectors: list[tuple[dict[str, Any], list[dict[str, Any]], list[list[float]]]] = []
        for listing_data, chunks in prepared:
            count = len(chunks)
            with_vectors.append((listing_data, chunks, flat_vectors[cursor : cursor + count]))
            cursor += count

        # Phase 3: persist within a single session per batch.
        async with async_session() as session:
            for listing_data, chunks, vectors in with_vectors:
                try:
                    listing = await upsert_listing(session, listing_data)
                    chunk_rows = prepare_listing_chunks(listing.id, chunks, vectors)
                    await session.execute(
                        delete(Chunk).where(
                            Chunk.parent_type == "listing",
                            Chunk.parent_id == listing.id,
                        )
                    )
                    session.add_all([Chunk(**chunk_row) for chunk_row in chunk_rows])
                    inserted_or_updated += 1
                    chunks_inserted += len(chunk_rows)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    errors += 1
                    print(
                        f"[ingest] db write failed for {listing_data.get('product_id', '?')}: {exc}",
                        file=sys.stderr,
                    )
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
