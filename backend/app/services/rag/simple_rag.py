"""Simple pgvector + Gemini RAG pipeline for the chat endpoint."""

from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.listing import Listing


TOP_K_DEFAULT = 5
EMBEDDING_DIMENSIONS = 768


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
        filters["property_type"] = "Căn hộ"
    elif "nha rieng" in normalized or "nha pho" in normalized:
        filters["property_type"] = "Nhà"
    elif "dat" in normalized:
        filters["property_type"] = "Đất"

    city_aliases = [
        ("Hồ Chí Minh", ["ho chi minh", "tp hcm", "tphcm", "sai gon", "sai gon"]),
        ("Hà Nội", ["ha noi"]),
        ("Đà Nẵng", ["da nang"]),
        ("Bình Dương", ["binh duong"]),
        ("Đồng Nai", ["dong nai"]),
    ]
    for city, aliases in city_aliases:
        if any(alias in normalized for alias in aliases):
            filters["city"] = city
            break

    district_match = re.search(r"\b(quan|quận)\s*(\d{1,2})\b", query, flags=re.IGNORECASE)
    if district_match:
        filters["district"] = f"Quận {district_match.group(2)}"

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


def _apply_filters(statement, filters: dict[str, Any]):
    conditions = [Listing.is_active == True, Listing.embedding.is_not(None)]  # noqa: E712
    if filters.get("listing_type"):
        conditions.append(Listing.listing_type == filters["listing_type"])
    if filters.get("property_type"):
        conditions.append(Listing.property_type.ilike(f"%{filters['property_type']}%"))
    if filters.get("city"):
        conditions.append(Listing.city.ilike(f"%{filters['city']}%"))
    if filters.get("district"):
        conditions.append(Listing.district.ilike(f"%{filters['district']}%"))
    if filters.get("bedrooms") is not None:
        conditions.append(Listing.bedrooms == filters["bedrooms"])
    if filters.get("min_price") is not None:
        conditions.append(Listing.price >= filters["min_price"])
    if filters.get("max_price") is not None:
        conditions.append(Listing.price <= filters["max_price"])
    if filters.get("min_area") is not None:
        conditions.append(Listing.area >= filters["min_area"])
    if filters.get("max_area") is not None:
        conditions.append(Listing.area <= filters["max_area"])
    return statement.where(and_(*conditions))


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


def _format_listing_for_prompt(listing: Listing, index: int) -> str:
    parts = [
        f"{index}. {listing.title or 'Tin bất động sản'}",
        f"Loại: {listing.property_type or 'Không rõ'}",
        f"Vị trí: {', '.join(part for part in [listing.ward, listing.district, listing.city] if part) or 'Không rõ'}",
        f"Giá: {listing.price_text or 'Không rõ'}",
        f"Diện tích: {listing.area_text or 'Không rõ'}",
    ]
    if listing.bedrooms:
        parts.append(f"Phòng ngủ: {listing.bedrooms}")
    if listing.description:
        parts.append(f"Mô tả: {listing.description[:500]}")
    return "\n".join(parts)


def _build_answer_prompt(query: str, listings: Sequence[Listing]) -> str:
    listings_text = "\n\n".join(_format_listing_for_prompt(listing, index) for index, listing in enumerate(listings, start=1))
    return f"""Bạn là chatbot tư vấn bất động sản Việt Nam.

Câu hỏi của người dùng: {query}

Dữ liệu truy xuất được:
{listings_text}

Yêu cầu:
- Trả lời bằng tiếng Việt, ngắn gọn và thực tế.
- Chỉ dựa trên dữ liệu truy xuất được, không bịa thông tin ngoài nguồn.
- Nêu 3-5 lựa chọn nổi bật nếu có.
- Nhắc người dùng kiểm tra lại pháp lý/thông tin liên hệ trước khi giao dịch.
"""


def build_fallback_answer(query: str, listings: Sequence[Listing]) -> str:
    """Build a deterministic answer when the LLM generation step is unavailable."""
    lines = [
        f"Tìm thấy {len(listings)} tin bất động sản phù hợp với yêu cầu: \"{query}\".",
        "",
    ]
    for index, listing in enumerate(listings[:5], start=1):
        location = ", ".join(part for part in [listing.district, listing.city] if part) or "Chưa rõ vị trí"
        details = " - ".join(part for part in [listing.price_text, listing.area_text] if part)
        suffix = f" ({details})" if details else ""
        lines.append(f"{index}. {listing.title or 'Tin bất động sản'} - {location}{suffix}")
    lines.extend([
        "",
        "Lưu ý: vui lòng kiểm tra lại pháp lý, tình trạng tin đăng và thông tin liên hệ trước khi giao dịch.",
    ])
    return "\n".join(lines)


@dataclass
class GeminiClient:
    api_key: str
    model: str
    embedding_model: str

    def _client(self):
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("Thiếu dependency google-genai. Hãy cài backend requirements.") from exc
        return genai.Client(api_key=self.api_key)

    async def embed_text(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._embed_text_sync, text)

    def _embed_text_sync(self, text: str) -> list[float]:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY chưa được cấu hình.")
        from google.genai import types

        client = self._client()
        response = client.models.embed_content(
            model=self.embedding_model,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
        )
        embeddings = getattr(response, "embeddings", None)
        if embeddings:
            return list(embeddings[0].values)
        embedding = getattr(response, "embedding", None)
        if embedding:
            return list(embedding.values)
        raise RuntimeError("Gemini embedding response không có vector.")

    async def generate_answer(self, query: str, listings: Sequence[Listing]) -> str:
        return await asyncio.to_thread(self._generate_answer_sync, query, listings)

    def _generate_answer_sync(self, query: str, listings: Sequence[Listing]) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY chưa được cấu hình.")
        client = self._client()
        response = client.models.generate_content(
            model=self.model,
            contents=_build_answer_prompt(query, listings),
        )
        return getattr(response, "text", "") or "Không tạo được câu trả lời từ Gemini."


async def _retrieve_listings(
    db: AsyncSession,
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
) -> list[tuple[Listing, float]]:
    distance = Listing.embedding.cosine_distance(query_embedding).label("score")
    statement = select(Listing, distance)
    statement = _apply_filters(statement, filters).order_by(distance).limit(top_k)
    rows = (await db.execute(statement)).all()
    return [(listing, score) for listing, score in rows]


async def run_simple_rag(query: str, db: AsyncSession, top_k: int = TOP_K_DEFAULT) -> dict[str, Any]:
    """Run query embedding, pgvector retrieval, and Gemini answer generation."""
    settings = get_settings()
    client = GeminiClient(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_MODEL,
        embedding_model=settings.GEMINI_EMBEDDING_MODEL,
    )
    filters = extract_search_filters(query)
    query_embedding = await client.embed_text(query)
    ranked_listings = await _retrieve_listings(db, query_embedding, filters, top_k)

    if not ranked_listings:
        return {
            "final_response": "Tôi chưa tìm thấy tin bất động sản phù hợp trong dữ liệu đã được lập chỉ mục. Bạn có thể thử nới rộng khu vực, giá hoặc diện tích.",
            "agent_used": "simple_rag",
            "sources": [],
            "suggested_actions": ["Tìm khu vực khác", "Bỏ bớt điều kiện lọc", "Hỏi xu hướng giá khu vực"],
        }

    listings = [listing for listing, _score in ranked_listings]
    try:
        answer = await client.generate_answer(query, listings)
    except Exception:
        answer = build_fallback_answer(query, listings)
    return {
        "final_response": answer,
        "agent_used": "simple_rag",
        "sources": [format_listing_source(listing, score) for listing, score in ranked_listings],
        "suggested_actions": ["So sánh các lựa chọn", "Tìm thêm cùng khu vực", "Hỏi về pháp lý khi mua nhà"],
    }
