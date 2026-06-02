"""Legal advisor agent backed by legal knowledge-base chunks."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chatbot.contracts import AgentResult, RoutingDecision
from app.services.rag.hybrid_search import hybrid_search


LEGAL_SOURCES = [
    {
        "type": "legal_checklist",
        "title": "Checklist giao dich bat dong san",
        "summary": "Kiem tra chu so huu, quy hoach, dat coc, cong chung va sang ten.",
    }
]


def _format_legal_citation(record: dict[str, Any]) -> str:
    citation = record.get("citation") or {}
    slug = citation.get("doc_slug") or record.get("source") or record.get("title") or "nguon phap ly"
    parts = [str(slug)]
    if citation.get("dieu_number") is not None:
        parts.append(f"Dieu {citation['dieu_number']}")
    if citation.get("khoan_number") is not None:
        parts.append(f"Khoan {citation['khoan_number']}")
    return ", ".join(parts)


def _format_legal_source(record: dict[str, Any]) -> dict[str, Any]:
    matched_chunk = record.get("matched_chunk") or {}
    source = {
        "type": "legal_article",
        "id": record.get("id"),
        "title": record.get("title"),
        "category": record.get("category"),
        "source": record.get("source"),
        "url": record.get("url"),
        "citation": record.get("citation"),
    }
    if matched_chunk.get("distance") is not None:
        source["score"] = round(float(matched_chunk["distance"]), 4)
    return source


def _build_legal_answer(query: str, records: list[dict[str, Any]]) -> str:
    lines = [
        f"Ket qua tra cuu phap ly cho cau hoi: \"{query}\".",
        "Cac noi dung duoi day chi mang tinh tham khao va can doi chieu voi ho so goc/luat su khi giao dich.",
        "",
    ]
    for index, record in enumerate(records[:5], start=1):
        citation = _format_legal_citation(record)
        snippet = ((record.get("matched_chunk") or {}).get("text") or "").strip()
        if len(snippet) > 500:
            snippet = snippet[:500] + "..."
        lines.append(f"{index}. {citation}: {snippet or record.get('title') or 'Khong co trich doan'}")
    return "\n".join(lines)


async def run_legal_advisor(
    query: str,
    db: AsyncSession | None,
    routing: RoutingDecision | None,
) -> AgentResult:
    """Answer from legal KB chunks, falling back to a conservative checklist."""
    filters = dict(routing.search_filters if routing else {})
    filters["category"] = "legal"
    try:
        legal_records = await hybrid_search(
            query=query,
            filters=filters,
            parent_type="article",
            top_k=20,
            rerank_to=5,
        )
    except Exception:
        legal_records = []

    if legal_records:
        return AgentResult(
            agent_name="legal_advisor",
            content=_build_legal_answer(query, legal_records),
            sources=[_format_legal_source(record) for record in legal_records],
            suggested_actions=[
                "Doi chieu dieu luat lien quan",
                "Kiem tra ho so goc",
                "Hoi cong chung vien hoac luat su",
            ],
            confidence=0.8,
        )

    content = (
        "Ve phap ly, toi chua tim thay co so phap ly phu hop trong kho tri thuc da lap chi muc. "
        "Ban nen kiem tra toi thieu: thong tin chu so huu tren so, tinh trang quy hoach/tranh chap, "
        "dieu khoan dat coc, nghia vu thue phi, va lich cong chung/sang ten. Noi dung nay chi mang "
        "tinh tham khao; voi giao dich cu the nen doi chieu ho so goc va hoi cong chung vien hoac luat su."
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
