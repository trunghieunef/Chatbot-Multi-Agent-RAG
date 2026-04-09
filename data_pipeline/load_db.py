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
import re
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from sqlalchemy import select, text
from app.database import engine, async_session, Base
from app.models import Listing


PRICE_RE = re.compile(r"([\d.,]+)", re.IGNORECASE)


def parse_price_billion(text: str) -> float | None:
    """Parse Vietnamese price text to float (in billions)."""
    if not text:
        return None
    match = PRICE_RE.search(text)
    if not match:
        return None
    value = float(match.group(1).replace(".", "").replace(",", "."))
    lowered = text.lower()
    if "tỷ" in lowered or "ty" in lowered:
        return value
    if "triệu" in lowered or "tr/" in lowered:
        return value / 1000
    if "nghìn" in lowered or "ngàn" in lowered:
        return value / 1_000_000
    return value


def parse_area(text: str) -> float | None:
    """Parse area text to float (m²)."""
    if not text:
        return None
    match = re.search(r"([\d.,]+)\s*m", text, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(".", "").replace(",", "."))


def parse_int_safe(text: str) -> int | None:
    """Parse integer from text, return None on failure."""
    if not text:
        return None
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


def parse_price_per_m2(text: str) -> float | None:
    """Parse price per m2 text to float (in millions)."""
    if not text:
        return None
    match = PRICE_RE.search(text)
    if not match:
        return None
    return float(match.group(1).replace(".", "").replace(",", "."))


def determine_listing_type(row: dict) -> str:
    """Determine if listing is for sale or rent from title/url/price."""
    text = (row.get("title", "") + " " + row.get("url", "")).lower()
    if "cho thuê" in text or "cho-thue" in text or "thuê" in text:
        return "rent"
    if "/tháng" in row.get("price_text", "").lower():
        return "rent"
    return "sale"


def determine_property_type(row: dict) -> str:
    """Classify property type from title."""
    title = (row.get("title", "") + " " + row.get("property_type", "")).lower()
    if "căn hộ" in title or "chung cư" in title:
        return "Căn hộ chung cư"
    if "nhà riêng" in title or "nhà phố" in title:
        return "Nhà riêng"
    if "biệt thự" in title:
        return "Biệt thự"
    if "đất" in title or "đất nền" in title:
        return "Đất nền"
    if "shophouse" in title or "nhà phố thương mại" in title:
        return "Shophouse"
    if "văn phòng" in title:
        return "Văn phòng"
    if "kho" in title or "nhà xưởng" in title:
        return "Kho/Nhà xưởng"
    return row.get("property_type", "Khác") or "Khác"


def extract_location(row: dict) -> tuple[str, str, str]:
    """Extract ward, district, city from address field."""
    address = row.get("address", "") or ""
    parts = [p.strip() for p in address.split(",") if p.strip()]

    city = ""
    district = ""
    ward = ""

    if len(parts) >= 1:
        city = parts[-1]
    if len(parts) >= 2:
        district = parts[-2]
    if len(parts) >= 3:
        ward = parts[-3]

    return ward, district, city


def row_to_listing(row: dict) -> dict:
    """Convert a CSV row dict to a Listing model constructor kwargs."""
    ward, district, city = extract_location(row)

    return {
        "product_id": row.get("product_id", ""),
        "listing_type": determine_listing_type(row),
        "property_type": determine_property_type(row),
        "title": row.get("title", ""),
        "description": row.get("description", ""),
        "price": parse_price_billion(row.get("price_text", "")),
        "price_unit": "billion",
        "price_text": row.get("price_text", ""),
        "price_per_m2": parse_price_per_m2(row.get("price_per_m2_text", "")),
        "price_per_m2_text": row.get("price_per_m2_text", ""),
        "area": parse_area(row.get("area_text", "")),
        "area_text": row.get("area_text", ""),
        "bedrooms": parse_int_safe(row.get("bedrooms", "")),
        "bathrooms": parse_int_safe(row.get("bathrooms", "")),
        "floors": parse_int_safe(row.get("floors", "")),
        "direction": row.get("direction", "") or None,
        "balcony_direction": row.get("balcony_direction", "") or None,
        "frontage": row.get("frontage", "") or None,
        "road_width": row.get("road_width", "") or None,
        "legal_status": row.get("legal", "") or None,
        "furniture": row.get("furniture", "") or None,
        "address": row.get("address", "") or None,
        "ward": ward or None,
        "district": district or None,
        "city": city or None,
        "contact_name": row.get("contact_name", "") or None,
        "post_date": row.get("post_date", "") or None,
        "expiry_date": row.get("expiry_date", "") or None,
        "url": row.get("url", "") or None,
        "listing_type_label": row.get("listing_type", "") or None,
        "is_active": True,
    }


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
