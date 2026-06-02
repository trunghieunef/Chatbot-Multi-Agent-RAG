"""Investment advisor agent for conservative real-estate analysis."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chatbot.analytics import get_market_snapshot
from app.services.chatbot.contracts import AgentResult, RoutingDecision


def _fmt_number(value, digits: int = 2) -> str:
    return str(round(value, digits)) if value is not None else "chua ro"


def _estimate_rental_yield(sale_avg_billion: float | None, rent_avg_million: float | None) -> float | None:
    if not sale_avg_billion or not rent_avg_million:
        return None
    annual_rent_billion = rent_avg_million * 12 / 1000
    return round(annual_rent_billion / sale_avg_billion * 100, 1)


async def run_investment_advisor(
    query: str,
    db: AsyncSession,
    routing: RoutingDecision | None,
) -> AgentResult:
    """Provide non-financial-advice investment context from available listings."""
    filters = routing.search_filters if routing else {}
    sale_filters = {**filters, "listing_type": "sale"}
    rent_filters = {**filters, "listing_type": "rent"}
    sale_snapshot = await get_market_snapshot(db, sale_filters)
    rent_snapshot = await get_market_snapshot(db, rent_filters)
    rental_yield = _estimate_rental_yield(sale_snapshot["avg_price"], rent_snapshot["avg_price"])

    yield_text = (
        f"Rental yield uoc tinh khoang {rental_yield}%/nam neu gia thue trung binh "
        f"{_fmt_number(rent_snapshot['avg_price'])} trieu/thang."
        if rental_yield is not None
        else "Chua du du lieu gia thue de uoc tinh rental yield."
    )
    content = (
        f"Ve goc nhin dau tu, tap du lieu co {sale_snapshot['count']} tin ban de tham chieu. "
        f"Gia ban trung binh la {_fmt_number(sale_snapshot['avg_price'])} ty; "
        f"gia/m2 trung binh la {_fmt_number(sale_snapshot['avg_price_per_m2'])} trieu/m2. "
        f"{yield_text} "
        "Nen so sanh thanh khoan khu vuc, kha nang cho thue, phap ly va bien an toan dong tien. "
        "Day khong phai loi khuyen tai chinh chinh thuc."
    )
    return AgentResult(
        agent_name="investment_advisor",
        content=content,
        sources=[
            {
                "type": "investment_aggregate",
                "filters": filters,
                "sale": sale_snapshot,
                "rent": rent_snapshot,
                "rental_yield_percent": rental_yield,
            }
        ],
        suggested_actions=["Tinh dong tien cho thue", "So sanh ROI", "Kiem tra rui ro phap ly"],
        confidence=0.75 if sale_snapshot["count"] else 0.35,
    )
