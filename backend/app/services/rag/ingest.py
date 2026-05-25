"""Helpers for loading Hugging Face real estate rows into Listing records."""

from __future__ import annotations

import re
from typing import Any


PRICE_RE = re.compile(r"([\d.,]+)")


def _first_text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _first_number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, (int, float)):
            return float(value)
        match = PRICE_RE.search(str(value))
        if match:
            return float(match.group(1).replace(".", "").replace(",", "."))
    return None


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _format_measurement(value: float | None, unit: str) -> str | None:
    if value is None:
        return None
    return f"{_format_number(value)} {unit}"


def normalize_price_billion(value: Any) -> float | None:
    """Normalize a dataset price value to billion VND."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return round(numeric / 1_000_000_000, 4) if numeric > 1_000_000 else numeric

    text = str(value).lower()
    match = PRICE_RE.search(text)
    if not match:
        return None
    numeric = float(match.group(1).replace(".", "").replace(",", "."))
    if "tỷ" in text or "ty" in text:
        return numeric
    if "triệu" in text or "trieu" in text:
        return round(numeric / 1000, 4)
    if numeric > 1_000_000:
        return round(numeric / 1_000_000_000, 4)
    return numeric


def _price_per_m2_million(row: dict[str, Any], price_billion: float | None, area: float | None) -> float | None:
    explicit = _first_number(row, "price_per_m2", "price_per_m2_value")
    if explicit is not None:
        return round(explicit / 1_000_000, 2) if explicit > 1_000 else round(explicit, 2)
    if price_billion is None or area is None or area <= 0:
        return None
    return round((price_billion * 1_000) / area, 2)


def _build_product_id(row: dict[str, Any], row_index: int) -> str:
    candidate = _first_text(row, "id", "product_id", "post_id", "listing_id")
    if candidate:
        return f"hf-{candidate}"
    return f"hf-{row_index}"


def _detect_listing_type(row: dict[str, Any]) -> str:
    text = " ".join(
        value
        for value in [
            _first_text(row, "name", "title"),
            _first_text(row, "description"),
            _first_text(row, "transaction_type", "type_name", "listing_type"),
        ]
        if value
    ).lower()
    return "rent" if any(word in text for word in ["cho thuê", "thuê", "rent"]) else "sale"


def _build_address(row: dict[str, Any]) -> str | None:
    parts = [
        _first_text(row, "project_name"),
        _first_text(row, "street_name", "street"),
        _first_text(row, "ward_name", "ward"),
        _first_text(row, "district_name", "district"),
        _first_text(row, "province_name", "city", "province"),
    ]
    address = ", ".join(part for part in parts if part)
    return address or _first_text(row, "address")


def hf_row_to_listing_data(row: dict[str, Any], row_index: int) -> dict[str, Any]:
    """Map one Hugging Face dataset row to Listing constructor data."""
    price = normalize_price_billion(row.get("price") or row.get("price_value"))
    area = _first_number(row, "area", "area_value", "land_area")
    price_per_m2 = _price_per_m2_million(row, price, area)
    frontage = _format_measurement(_first_number(row, "frontage_width", "frontage"), "m")
    road_width = _format_measurement(_first_number(row, "road_width"), "m")

    return {
        "product_id": _build_product_id(row, row_index),
        "listing_type": _detect_listing_type(row),
        "property_type": _first_text(row, "property_type_name", "property_type"),
        "title": _first_text(row, "name", "title") or "",
        "description": _first_text(row, "description") or "",
        "price": price,
        "price_unit": "billion" if price is not None else None,
        "price_text": f"{_format_number(price)} tỷ" if price is not None else None,
        "price_per_m2": price_per_m2,
        "price_per_m2_text": f"{_format_number(price_per_m2)} triệu/m²" if price_per_m2 is not None else _first_text(row, "price_per_m2_text"),
        "area": area,
        "area_text": f"{_format_number(area)} m²" if area is not None else None,
        "bedrooms": int(_first_number(row, "bedroom_count", "bedrooms") or 0) or None,
        "bathrooms": int(_first_number(row, "bathroom_count", "bathrooms") or 0) or None,
        "floors": int(_first_number(row, "floor_count", "floors") or 0) or None,
        "direction": _first_text(row, "house_direction", "direction"),
        "balcony_direction": _first_text(row, "balcony_direction"),
        "frontage": frontage,
        "road_width": road_width,
        "legal_status": _first_text(row, "legal_status", "legal"),
        "furniture": _first_text(row, "furniture"),
        "address": _build_address(row),
        "ward": _first_text(row, "ward_name", "ward"),
        "district": _first_text(row, "district_name", "district"),
        "city": _first_text(row, "province_name", "city", "province"),
        "latitude": _first_number(row, "latitude", "lat"),
        "longitude": _first_number(row, "longitude", "lng", "lon"),
        "contact_name": _first_text(row, "contact_name"),
        "contact_phone": _first_text(row, "contact_phone", "phone"),
        "post_date": _first_text(row, "published_at", "post_date", "created_at"),
        "expiry_date": _first_text(row, "expired_at", "expiry_date"),
        "url": _first_text(row, "url", "source_url"),
        "listing_type_label": _first_text(row, "type_name", "listing_type_name"),
        "is_active": True,
    }


def build_listing_document(listing_data: dict[str, Any]) -> str:
    """Build the text that is embedded for semantic retrieval."""
    location = ", ".join(
        part
        for part in [
            listing_data.get("ward"),
            listing_data.get("district"),
            listing_data.get("city"),
        ]
        if part
    )
    fields = [
        listing_data.get("title"),
        listing_data.get("description"),
        listing_data.get("property_type"),
        location,
        listing_data.get("price_text"),
        listing_data.get("area_text"),
    ]
    if listing_data.get("bedrooms"):
        fields.append(f"{listing_data['bedrooms']} phòng ngủ")
    if listing_data.get("bathrooms"):
        fields.append(f"{listing_data['bathrooms']} phòng tắm")
    return "\n".join(str(field) for field in fields if field)
