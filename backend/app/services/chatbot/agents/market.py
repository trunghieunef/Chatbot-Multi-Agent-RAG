"""Market analysis agent backed by SQL aggregates."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.listing import Listing
from app.services.chatbot.contracts import AgentResult, RoutingDecision


async def run_market_analysis(
    query: str,
    db: AsyncSession,
    routing: RoutingDecision | None,
) -> AgentResult:
    """Summarize current market statistics from listing data."""
    filters = routing.search_filters if routing else {}
    statement = select(
        func.count(Listing.id),
        func.avg(Listing.price),
        func.avg(Listing.area),
        func.avg(Listing.price_per_m2),
    ).where(Listing.is_active == True)
    if filters.get("city"):
        statement = statement.where(Listing.city.ilike(f"%{filters['city']}%"))
    if filters.get("district"):
        statement = statement.where(Listing.district.ilike(f"%{filters['district']}%"))
    if filters.get("listing_type"):
        statement = statement.where(Listing.listing_type == filters["listing_type"])

    row = (await db.execute(statement)).one()
    total, avg_price, avg_area, avg_price_per_m2 = row
    content = (
        f"Du lieu hien co ghi nhan {total or 0} tin dang phu hop. "
        f"Gia trung binh khoang {round(avg_price, 2) if avg_price else 'chua ro'} ty, "
        f"dien tich trung binh {round(avg_area, 1) if avg_area else 'chua ro'} m2, "
        f"gia/m2 trung binh {round(avg_price_per_m2, 2) if avg_price_per_m2 else 'chua ro'} trieu/m2. "
        "Nen xem day la chi bao tham khao vi du lieu phu thuoc vao chat luong tin dang."
    )
    return AgentResult(
        agent_name="market_analysis",
        content=content,
        sources=[{"type": "market_aggregate", "filters": filters, "count": total or 0}],
        suggested_actions=["So sanh theo quan", "Loc theo loai hinh", "Xem tin dang noi bat"],
        confidence=0.75,
    )
