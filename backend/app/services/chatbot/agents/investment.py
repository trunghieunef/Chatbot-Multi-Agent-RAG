"""Investment advisor agent for conservative real-estate analysis."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.listing import Listing
from app.services.chatbot.contracts import AgentResult, RoutingDecision


async def run_investment_advisor(
    query: str,
    db: AsyncSession,
    routing: RoutingDecision | None,
) -> AgentResult:
    """Provide non-financial-advice investment context from available listings."""
    filters = routing.search_filters if routing else {}
    statement = select(func.count(Listing.id), func.avg(Listing.price), func.avg(Listing.price_per_m2)).where(
        Listing.is_active == True,
        Listing.price.isnot(None),
    )
    if filters.get("city"):
        statement = statement.where(Listing.city.ilike(f"%{filters['city']}%"))
    if filters.get("district"):
        statement = statement.where(Listing.district.ilike(f"%{filters['district']}%"))

    row = (await db.execute(statement)).one()
    total, avg_price, avg_price_per_m2 = row
    content = (
        f"Ve goc nhin dau tu, tap du lieu co {total or 0} tin co gia de tham chieu. "
        f"Gia trung binh la {round(avg_price, 2) if avg_price else 'chua ro'} ty; "
        f"gia/m2 trung binh la {round(avg_price_per_m2, 2) if avg_price_per_m2 else 'chua ro'} trieu/m2. "
        "Nen so sanh thanh khoan khu vuc, kha nang cho thue, phap ly va bien an toan dong tien. "
        "Day khong phai loi khuyen tai chinh chinh thuc."
    )
    return AgentResult(
        agent_name="investment_advisor",
        content=content,
        sources=[{"type": "investment_aggregate", "filters": filters, "count": total or 0}],
        suggested_actions=["Tinh dong tien cho thue", "So sanh ROI", "Kiem tra rui ro phap ly"],
        confidence=0.7,
    )
