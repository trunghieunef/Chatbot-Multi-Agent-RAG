from __future__ import annotations

import re
from typing import Any


INTENT_RULES: dict[str, tuple[str, ...]] = {
    "gần trường": ("gần trường", "trường học", "đại học", "mầm non"),
    "gần chợ": ("gần chợ", "chợ", "siêu thị", "trung tâm thương mại"),
    "gần bệnh viện": ("bệnh viện", "phòng khám"),
    "an ninh": ("an ninh", "bảo vệ", "camera"),
    "view đẹp": ("view", "ban công", "sông", "công viên"),
    "pháp lý rõ": ("sổ hồng", "sổ đỏ", "pháp lý"),
}


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def extract_intent_tags(text: str) -> list[str]:
    lowered = text.lower()
    tags: list[str] = []
    for tag, needles in INTENT_RULES.items():
        if any(needle in lowered for needle in needles):
            tags.append(tag)
    return tags


def build_listing_chunks(listing: dict[str, Any]) -> list[dict[str, str]]:
    title = compact_text(listing.get("title"))
    property_type = compact_text(listing.get("property_type"))
    listing_type = compact_text(listing.get("listing_type"))
    price_text = compact_text(listing.get("price_text"))
    area_text = compact_text(listing.get("area_text"))
    district = compact_text(listing.get("district"))
    city = compact_text(listing.get("city"))
    address = compact_text(listing.get("address"))
    description = compact_text(listing.get("description"))
    legal_status = compact_text(listing.get("legal_status"))
    furniture = compact_text(listing.get("furniture"))
    bedrooms = compact_text(listing.get("bedrooms"))
    bathrooms = compact_text(listing.get("bathrooms"))

    chunks: list[dict[str, str]] = []

    overview_parts = [
        title,
        f"Loại giao dịch: {listing_type}" if listing_type else "",
        f"Loại bất động sản: {property_type}" if property_type else "",
        f"Giá: {price_text}" if price_text else "",
        f"Diện tích: {area_text}" if area_text else "",
        f"Phòng ngủ: {bedrooms}" if bedrooms else "",
        f"Phòng tắm: {bathrooms}" if bathrooms else "",
        f"Khu vực: {district}, {city}".strip(", ") if district or city else "",
        f"Pháp lý: {legal_status}" if legal_status else "",
        f"Nội thất: {furniture}" if furniture else "",
    ]
    overview = ". ".join(part for part in overview_parts if part)
    if overview:
        chunks.append({"chunk_type": "overview", "text": overview})

    if description:
        chunks.append({"chunk_type": "description", "text": description})

    location_parts = [
        f"Địa chỉ: {address}" if address else "",
        f"Quận/Huyện: {district}" if district else "",
        f"Tỉnh/Thành phố: {city}" if city else "",
    ]
    location = ". ".join(part for part in location_parts if part)
    if location:
        chunks.append({"chunk_type": "location", "text": location})

    tags = extract_intent_tags(" ".join([title, description, address, legal_status, furniture]))
    if tags:
        chunks.append({"chunk_type": "intent_tags", "text": "Nhu cầu phù hợp: " + ", ".join(tags)})

    return chunks
