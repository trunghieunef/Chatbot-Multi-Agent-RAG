"""Property search agent backed by the existing pgvector retrieval path."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chatbot.contracts import AgentResult, RoutingDecision
from app.services.rag.simple_rag import (
    GeminiClient,
    _retrieve_listings,
    build_fallback_answer,
    format_listing_source,
)
from app.config import get_settings


async def run_property_search(
    query: str,
    db: AsyncSession,
    routing: RoutingDecision | None,
) -> AgentResult:
    """Find matching listings and summarize them for the user."""
    settings = get_settings()
    client = GeminiClient(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_MODEL,
        embedding_model=settings.GEMINI_EMBEDDING_MODEL,
    )
    try:
        query_embedding = await client.embed_text(query)
        ranked = await _retrieve_listings(db, query_embedding, (routing.search_filters if routing else {}), top_k=5)
    except RuntimeError:
        ranked = []

    if not ranked:
        return AgentResult(
            agent_name="property_search",
            content="Toi chua tim thay tin dang phu hop trong du lieu da lap chi muc. Hay thu noi rong khu vuc, muc gia hoac dien tich.",
            sources=[],
            suggested_actions=["Noi rong khu vuc", "Bo bot dieu kien loc", "Hoi xu huong gia khu vuc"],
            confidence=0.4,
        )

    listings = [listing for listing, _score in ranked]
    try:
        content = await client.generate_answer(query, listings)
    except Exception:
        content = build_fallback_answer(query, listings)

    return AgentResult(
        agent_name="property_search",
        content=content,
        sources=[format_listing_source(listing, score) for listing, score in ranked],
        suggested_actions=["So sanh cac lua chon", "Tim them cung khu vuc", "Hoi ve phap ly khi mua nha"],
        confidence=0.85,
    )
