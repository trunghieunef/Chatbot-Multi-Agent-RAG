"""Market analysis agent backed by SQL aggregates."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chatbot.analytics import get_district_comparison, get_market_snapshot
from app.services.chatbot.contracts import AgentResult, RoutingDecision


def _fmt_number(value, digits: int = 2) -> str:
    return str(round(value, digits)) if value is not None else "chua ro"


async def run_market_analysis(
    query: str,
    db: AsyncSession,
    routing: RoutingDecision | None,
) -> AgentResult:
    """Summarize current market statistics from listing data."""
    filters = routing.search_filters if routing else {}
    snapshot = await get_market_snapshot(db, filters)
    comparison = await get_district_comparison(db, filters, limit=5)

    lines = [
        f"Du lieu hien co ghi nhan {snapshot['count']} tin dang phu hop.",
        (
            f"Gia trung binh khoang {_fmt_number(snapshot['avg_price'])} ty, "
            f"dien tich trung binh {_fmt_number(snapshot['avg_area'], 1)} m2, "
            f"gia/m2 trung binh {_fmt_number(snapshot['avg_price_per_m2'])} trieu/m2."
        ),
    ]
    if comparison:
        lines.append("So sanh nhanh theo quan:")
        for row in comparison:
            lines.append(
                f"- {row['district']}: {row['count']} tin, "
                f"gia TB {_fmt_number(row['avg_price'])} ty, "
                f"gia/m2 TB {_fmt_number(row['avg_price_per_m2'])} trieu/m2."
            )
    lines.append("Nen xem day la chi bao tham khao vi du lieu phu thuoc vao chat luong tin dang.")
    return AgentResult(
        agent_name="market_analysis",
        content="\n".join(lines),
        sources=[
            {"type": "market_aggregate", "filters": filters, **snapshot},
            {"type": "district_comparison", "filters": filters, "items": comparison},
        ],
        suggested_actions=["So sanh theo quan", "Loc theo loai hinh", "Xem tin dang noi bat"],
        confidence=0.75 if snapshot["count"] else 0.35,
    )
