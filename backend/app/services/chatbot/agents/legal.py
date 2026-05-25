"""Legal advisor agent for real-estate safety checklists."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chatbot.contracts import AgentResult, RoutingDecision


LEGAL_SOURCES = [
    {
        "type": "legal_checklist",
        "title": "Checklist giao dich bat dong san",
        "summary": "Kiem tra chu so huu, quy hoach, dat coc, cong chung va sang ten.",
    }
]


async def run_legal_advisor(
    query: str,
    db: AsyncSession | None,
    routing: RoutingDecision | None,
) -> AgentResult:
    """Return a conservative legal checklist without pretending to be legal counsel."""
    content = (
        "Ve phap ly, ban nen kiem tra toi thieu: thong tin chu so huu tren so, "
        "tinh trang quy hoach/tranh chap, dieu khoan dat coc, nghia vu thue phi, "
        "va lich cong chung/sang ten. Noi dung nay chi mang tinh tham khao; "
        "voi giao dich cu the nen doi chieu ho so goc va hoi cong chung vien hoac luat su."
    )
    return AgentResult(
        agent_name="legal_advisor",
        content=content,
        sources=LEGAL_SOURCES,
        suggested_actions=[
            "Kiem tra so do va quy hoach",
            "Lap checklist dat coc",
            "Hoi ve thue phi sang ten",
        ],
        confidence=0.65,
    )
