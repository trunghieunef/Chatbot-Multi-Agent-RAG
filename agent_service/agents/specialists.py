from __future__ import annotations

from typing import Any


def _readiness_status(readiness: dict[str, Any], key: str) -> str:
    value = readiness.get(key, {})
    if isinstance(value, dict):
        return str(value.get("status", "unknown"))
    return "unknown"


def _record_location(record: dict[str, Any]) -> str | None:
    parts = [
        record.get("district"),
        record.get("city"),
        record.get("province"),
        record.get("location"),
    ]
    values = [str(part) for part in parts if part]
    return ", ".join(dict.fromkeys(values)) or None


def _source_from_record(record: dict[str, Any], source_type: str) -> dict[str, Any]:
    metadata = {
        key: record.get(key)
        for key in ("price_text", "area_text", "category")
        if record.get(key) is not None
    }
    return {
        "type": source_type,
        "id": record.get("id"),
        "product_id": record.get("product_id"),
        "title": record.get("title"),
        "url": record.get("url"),
        "location": _record_location(record),
        "citation": record.get("citation"),
        "score": record.get("score"),
        "metadata": metadata,
    }


def _describe_record(record: dict[str, Any]) -> str:
    details = [str(record.get("title") or "Nguon khong co tieu de")]
    location = _record_location(record)
    if location:
        details.append(location)
    if record.get("price_text"):
        details.append(str(record["price_text"]))
    if record.get("area_text"):
        details.append(str(record["area_text"]))
    return " - ".join(details)


def _agent_result(
    *,
    agent_name: str,
    content: str,
    sources: list[dict[str, Any]] | None = None,
    confidence: float,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "agent_name": agent_name,
        "content": content,
        "sources": sources or [],
        "confidence": confidence,
        "warnings": warnings or [],
    }


async def run_property_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    if not evidence:
        return _agent_result(
            agent_name="property_search",
            content=(
                "Chua co bang chung listing phu hop de khang dinh bat dong san cu the. "
                "Toi chi co the goi y bo sung tieu chi tim kiem truoc khi so sanh."
            ),
            confidence=0.35,
            warnings=["no_listing_evidence"],
        )

    lines = [_describe_record(record) for record in evidence]
    content = (
        "Cac listing phu hop voi yeu cau:\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\nThong tin duoc rut ra tu nguon listing kem theo; can kiem tra lai tinh trang va gia truoc khi giao dich."
    )
    return _agent_result(
        agent_name="property_search",
        content=content,
        sources=[_source_from_record(record, "listing") for record in evidence],
        confidence=0.8,
    )


async def run_project_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    if _readiness_status(readiness, "projects") != "ready" and not evidence:
        return _agent_result(
            agent_name="project_agent",
            content="Nguon du an chua san sang, nen toi chua co du bang chung de danh gia du an cu the.",
            confidence=0.3,
            warnings=["project_source_not_ready"],
        )

    content = "Thong tin du an lien quan:\n" + "\n".join(
        f"- {_describe_record(record)}" for record in evidence
    )
    return _agent_result(
        agent_name="project_agent",
        content=content,
        sources=[_source_from_record(record, "project") for record in evidence],
        confidence=0.75 if evidence else 0.4,
    )


async def run_market_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    content = "Phan tich thi truong hien chi la snapshot tai thoi diem truy van, khong phai chuoi thoi gian day du."
    if evidence:
        content += "\nCac diem du lieu lien quan:\n" + "\n".join(
            f"- {_describe_record(record)}" for record in evidence
        )
    return _agent_result(
        agent_name="market_analysis",
        content=content,
        sources=[_source_from_record(record, "market_snapshot") for record in evidence],
        confidence=0.65 if evidence else 0.45,
        warnings=["market_snapshot_not_time_series"],
    )


async def run_news_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    if not evidence:
        return _agent_result(
            agent_name="news_agent",
            content="Chua co bang chung tin tuc de tom tat cap nhat lien quan.",
            confidence=0.35,
            warnings=["no_news_evidence"],
        )

    content = "Tin tuc lien quan:\n" + "\n".join(
        f"- {_describe_record(record)}" for record in evidence
    )
    return _agent_result(
        agent_name="news_agent",
        content=content,
        sources=[_source_from_record(record, "news_article") for record in evidence],
        confidence=0.75,
    )


async def run_legal_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    if _readiness_status(readiness, "legal") != "ready" and not evidence:
        return _agent_result(
            agent_name="legal_advisor",
            content=(
                "Kho tri thuc phap ly chua san sang, nen cau tra loi chi mang tinh tham khao. "
                "Vui long doi chieu van ban hien hanh hoac hoi chuyen gia phap ly truoc khi thuc hien."
            ),
            confidence=0.3,
            warnings=["legal_kb_not_ready"],
        )

    content = (
        "Thong tin phap ly tham khao:\n"
        + "\n".join(f"- {_describe_record(record)}" for record in evidence)
        + "\nNoi dung nay chi de tham khao, khong thay the tu van phap ly chuyen nghiep."
    )
    return _agent_result(
        agent_name="legal_advisor",
        content=content,
        sources=[_source_from_record(record, "legal_article") for record in evidence],
        confidence=0.75 if evidence else 0.4,
    )


async def run_investment_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    risk_preference = preferences.get("risk_preferences", {})
    if isinstance(risk_preference, dict):
        risk_value = risk_preference.get("value", "chua ro")
    else:
        risk_value = risk_preference or "chua ro"

    content = (
        f"Khau vi rui ro hien ghi nhan: {risk_value}. "
        "Nhan dinh dau tu nay khong phai loi khuyen tai chinh; can tu tham dinh dong tien, phap ly va kha nang vay."
    )
    if evidence:
        content += "\nBang chung lien quan:\n" + "\n".join(
            f"- {_describe_record(record)}" for record in evidence
        )

    return _agent_result(
        agent_name="investment_advisor",
        content=content,
        sources=[_source_from_record(record, "investment_evidence") for record in evidence],
        confidence=0.65 if evidence else 0.45,
        warnings=["not_financial_advice"],
    )
