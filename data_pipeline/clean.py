"""
Listing cleaning utilities: parse and normalize raw CSV fields into Listing kwargs.

Provides parsers for Vietnamese price/area text, listing/property type classification,
location extraction, and a high-level row_to_listing converter.
"""

import json
import re
import unicodedata
from datetime import date


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
    listing_type = determine_listing_type(row)

    price_text = row.get("price_text", "") or ""
    price_unit = "billion"
    if listing_type == "rent" and "tháng" in price_text.lower():
        price_unit = "million/month"

    return {
        "product_id": row.get("product_id", ""),
        "listing_type": listing_type,
        "property_type": determine_property_type(row),
        "title": row.get("title", ""),
        "description": row.get("description", ""),
        "price": parse_price_billion(row.get("price_text", "")),
        "price_unit": price_unit,
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


def row_to_project(row: dict) -> dict:
    """Convert a project CSV row dict into Project model kwargs.

    Tolerates missing/blank fields, JSON-encoded amenities lists, and
    non-numeric ``total_units`` values.
    """
    raw_amenities = row.get("amenities") or "[]"
    try:
        amenities = (
            json.loads(raw_amenities)
            if isinstance(raw_amenities, str)
            else list(raw_amenities)
        )
    except json.JSONDecodeError:
        amenities = []

    total_units_value = row.get("total_units")
    try:
        total_units = (
            int(total_units_value) if total_units_value not in (None, "") else None
        )
    except (TypeError, ValueError):
        total_units = None

    return {
        "slug": (row.get("slug") or "").strip(),
        "name": (row.get("name") or "").strip(),
        "developer": (row.get("developer") or "").strip() or None,
        "location": row.get("location") or None,
        "district": row.get("district") or None,
        "city": row.get("city") or None,
        "total_units": total_units,
        "price_range": row.get("price_range") or None,
        "area_range": row.get("area_range") or None,
        "status": row.get("status") or None,
        "project_type": row.get("project_type") or None,
        "description": row.get("description") or None,
        "amenities": [str(item).strip() for item in amenities if str(item).strip()],
        "url": row.get("url") or None,
    }


def _parse_iso_date(value: str) -> date | None:
    """Return a ``date`` from an ISO ``YYYY-MM-DD`` string, or ``None`` if unparseable."""
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def row_to_article(row: dict) -> dict:
    """Convert a news/article CSV row dict into Article model kwargs."""
    return {
        "title": (row.get("title") or "").strip(),
        "body": (row.get("body") or "").strip(),
        "category": (row.get("category") or "news").strip() or "news",
        "source": (row.get("source") or "").strip() or "batdongsan.com",
        "post_date": _parse_iso_date(row.get("post_date") or ""),
        "url": row.get("url") or None,
    }



def slugify(value: str) -> str:
    """Lowercase, strip diacritics, replace non-alphanumeric runs with hyphens."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFD", value)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    without_marks = without_marks.replace("đ", "d").replace("Đ", "d")
    lowered = without_marks.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return cleaned
