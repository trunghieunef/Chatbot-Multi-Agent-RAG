"""
Data loader: Import CSV data into PostgreSQL.

Reads listing_details.csv and apartments.csv, normalizes fields,
and inserts them into the listings table.

Usage:
    python -m data_pipeline.load_db
    python -m data_pipeline.load_db --csv ../data/listing_details.csv
"""

import argparse
import csv
import os
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from sqlalchemy import select, text
from app.database import engine, async_session, Base
from app.models import Listing
from data_pipeline.clean import row_to_listing


async def load_csv_to_db(csv_path: str, batch_size: int = 200):
    """Load a CSV file into the listings table."""
    if not os.path.exists(csv_path):
        print(f"❌ File not found: {csv_path}")
        return

    # Enable pgvector extension
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database schema ready")

    # Read CSV
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"📄 Read {len(rows)} rows from {csv_path}")

    # Get existing product_ids
    async with async_session() as session:
        result = await session.execute(select(Listing.product_id))
        existing_ids = {row[0] for row in result.all()}
    print(f"📋 {len(existing_ids)} listings already in database")

    # Filter new rows
    new_rows = [r for r in rows if r.get("product_id") and r["product_id"] not in existing_ids]
    print(f"🆕 {len(new_rows)} new listings to insert")

    if not new_rows:
        print("✅ Nothing new to insert!")
        return

    # Insert in batches
    inserted = 0
    errors = 0
    for i in range(0, len(new_rows), batch_size):
        batch = new_rows[i : i + batch_size]
        async with async_session() as session:
            for row in batch:
                try:
                    listing_data = row_to_listing(row)
                    listing = Listing(**listing_data)
                    session.add(listing)
                    inserted += 1
                except Exception as e:
                    errors += 1
                    if errors <= 5:
                        print(f"  ⚠️ Error on {row.get('product_id', '?')}: {e}")

            await session.commit()
        print(f"  Batch {i // batch_size + 1}: inserted {len(batch)} ({inserted} total)")

    print(f"\n✅ Done! Inserted {inserted} listings ({errors} errors)")


async def main():
    parser = argparse.ArgumentParser(description="Load CSV data into PostgreSQL")
    parser.add_argument(
        "--csv",
        default=os.path.join(os.path.dirname(__file__), "..", "data", "listing_details.csv"),
        help="Path to the CSV file to load",
    )
    parser.add_argument("--batch-size", type=int, default=200, help="Insert batch size")
    args = parser.parse_args()

    csv_path = os.path.normpath(os.path.abspath(args.csv))
    await load_csv_to_db(csv_path, args.batch_size)


if __name__ == "__main__":
    asyncio.run(main())
