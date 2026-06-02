"""Shared listing formatting and filter helpers for chatbot agents."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Sequence

from app.models.listing import Listing


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn").lower()


def _extract_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def extract_search_filters(query: str) -> dict[str, Any]:
    """Extract conservative structured filters from a Vietnamese query."""
    normalized = _strip_accents(query)
    filters: dict[str, Any] = {}

    if any(word in normalized for word in ["thue", "cho thue"]):
        filters["listing_type"] = "rent"
    elif any(word in normalized for word in ["mua", "ban", "tim"]):
        filters["listing_type"] = "sale"

    if any(word in normalized for word in ["can ho", "chung cu"]):
        filters["property_type"] = "Can ho"
    elif "nha rieng" in normalized or "nha pho" in normalized:
        filters["property_type"] = "Nha"
    elif "dat" in normalized:
        filters["property_type"] = "Dat"

    city_aliases = [
        ("Ho Chi Minh", ["ho chi minh", "tp hcm", "tphcm", "sai gon", "saigon"]),
        ("Ha Noi", ["ha noi"]),
        ("Da Nang", ["da nang"]),
        ("Binh Duong", ["binh duong"]),
        ("Dong Nai", ["dong nai"]),
    ]
    for city, aliases in city_aliases:
        if any(alias in normalized for alias in aliases):
            filters["city"] = city
            break

    district_match = re.search(r"\b(quan|quận)\s*(\d{1,2})\b", query, flags=re.IGNORECASE)
    if district_match:
        filters["district"] = f"Quan {district_match.group(2)}"

    bedrooms = re.search(r"(\d+)\s*(pn|phong ngu|phòng ngủ)", query, flags=re.IGNORECASE)
    if bedrooms:
        filters["bedrooms"] = int(bedrooms.group(1))

    max_price = _extract_float(r"(?:duoi|toi da|khong qua)\s*(\d+(?:[\.,]\d+)?)\s*(?:ty|ti|tỷ)", normalized)
    if max_price is not None:
        filters["max_price"] = max_price

    min_price = _extract_float(r"(?:tu|tren)\s*(\d+(?:[\.,]\d+)?)\s*(?:ty|ti|tỷ)", normalized)
    if min_price is not None:
        filters["min_price"] = min_price

    min_area = _extract_float(r"(?:dien tich tu|tu)\s*(\d+(?:[\.,]\d+)?)\s*m2", normalized)
    if min_area is not None:
        filters["min_area"] = min_area

    max_area = _extract_float(r"(?:dien tich duoi|duoi)\s*(\d+(?:[\.,]\d+)?)\s*m2", normalized)
    if max_area is not None:
        filters["max_area"] = max_area

    return filters


def format_listing_source(listing: Listing, score: float | None = None) -> dict[str, Any]:
    """Return source metadata safe for chat responses."""
    location = ", ".join(part for part in [listing.district, listing.city] if part)
    source = {
        "id": listing.id,
        "product_id": listing.product_id,
        "title": listing.title,
        "location": location or None,
        "price_text": listing.price_text,
        "area_text": listing.area_text,
        "published_at": listing.post_date,
    }
    if score is not None:
        source["score"] = round(float(score), 4)
    return source


def build_fallback_answer(query: str, listings: Sequence[Listing]) -> str:
    """Build a deterministic answer from listing ORM rows."""
    lines = [
        f'Tim thay {len(listings)} tin bat dong san phu hop voi yeu cau: "{query}".',
        "",
    ]
    for index, listing in enumerate(listings[:5], start=1):
        location = ", ".join(part for part in [listing.district, listing.city] if part) or "Chua ro vi tri"
        details = " - ".join(part for part in [listing.price_text, listing.area_text] if part)
        suffix = f" ({details})" if details else ""
        lines.append(f"{index}. {listing.title or 'Tin bat dong san'} - {location}{suffix}")
    lines.extend([
        "",
        "Luu y: vui long kiem tra lai phap ly, tinh trang tin dang va thong tin lien he truoc khi giao dich.",
    ])
    return "\n".join(lines)


def format_listing_record_source(record: dict[str, Any]) -> dict[str, Any]:
    """Return public source metadata from a hybrid_search listing record."""
    location = ", ".join(part for part in [record.get("district"), record.get("city")] if part)
    matched_chunk = record.get("matched_chunk") or {}
    source = {
        "type": "listing",
        "id": record.get("id"),
        "product_id": record.get("product_id"),
        "title": record.get("title"),
        "location": location or None,
        "price_text": record.get("price_text"),
        "area_text": record.get("area_text"),
        "published_at": record.get("post_date") or record.get("published_at"),
    }
    score = matched_chunk.get("rerank_score")
    if score is None:
        score = matched_chunk.get("distance")
    if score is not None:
        source["score"] = round(float(score), 4)
    if record.get("url"):
        source["url"] = record["url"]
    return source


def build_record_fallback_answer(query: str, listings: Sequence[dict[str, Any]]) -> str:
    """Build a deterministic answer from hybrid_search listing records."""
    lines = [
        f'Tim thay {len(listings)} tin bat dong san phu hop voi yeu cau: "{query}".',
        "",
    ]
    for index, listing in enumerate(listings[:5], start=1):
        location = ", ".join(part for part in [listing.get("district"), listing.get("city")] if part) or "Chua ro vi tri"
        details = " - ".join(part for part in [listing.get("price_text"), listing.get("area_text")] if part)
        suffix = f" ({details})" if details else ""
        lines.append(f"{index}. {listing.get('title') or 'Tin bat dong san'} - {location}{suffix}")
    lines.extend([
        "",
        "Luu y: vui long kiem tra lai phap ly, tinh trang tin dang va thong tin lien he truoc khi giao dich.",
    ])
    return "\n".join(lines)
