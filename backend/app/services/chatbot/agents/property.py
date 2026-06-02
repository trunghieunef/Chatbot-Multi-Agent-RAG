"""Property search agent backed by chunk-based hybrid retrieval."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chatbot.contracts import AgentResult, RoutingDecision
from app.services.rag.simple_rag import (
    build_record_fallback_answer,
    format_listing_record_source,
)
from app.services.rag.hybrid_search import hybrid_search


async def run_property_search(
    query: str,
    db: AsyncSession,
    routing: RoutingDecision | None,
) -> AgentResult:
    """Find matching listings and summarize them for the user."""
    filters = routing.search_filters if routing else {}
    try:
        listings = await hybrid_search(
            query=query,
            filters=filters,
            parent_type="listing",
            top_k=20,
            rerank_to=5,
        )
    except Exception:
        listings = []

    if not listings:
        return AgentResult(
            agent_name="property_search",
            content="Toi chua tim thay tin dang phu hop trong du lieu da lap chi muc. Hay thu noi rong khu vuc, muc gia hoac dien tich.",
            sources=[],
            suggested_actions=["Noi rong khu vuc", "Bo bot dieu kien loc", "Hoi xu huong gia khu vuc"],
            confidence=0.4,
        )

    return AgentResult(
        agent_name="property_search",
        content=build_record_fallback_answer(query, listings),
        sources=[format_listing_record_source(listing) for listing in listings],
        suggested_actions=["So sanh cac lua chon", "Tim them cung khu vuc", "Hoi ve phap ly khi mua nha"],
        confidence=0.85,
    )
