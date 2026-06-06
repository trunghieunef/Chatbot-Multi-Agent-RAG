from __future__ import annotations

from typing import Any

from agent_service.contracts import StructuredWarning


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
    metadata = {}
    price_text = record.get("price_text") or record.get("price_range")
    area_text = record.get("area_text") or record.get("area_range")
    if price_text is not None:
        metadata["price_text"] = price_text
    if area_text is not None:
        metadata["area_text"] = area_text
    if record.get("category") is not None:
        metadata["category"] = record.get("category")

    matched_chunk = record.get("matched_chunk") or {}
    rerank_score = (
        matched_chunk.get("rerank_score") if isinstance(matched_chunk, dict) else None
    )
    return {
        "type": source_type,
        "id": record.get("id"),
        "product_id": record.get("product_id"),
        "title": record.get("title") or record.get("name"),
        "url": record.get("url"),
        "location": _record_location(record),
        "citation": record.get("citation"),
        "score": rerank_score,
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
    status: str,
    evidence_ids_used: list[str] | None = None,
    sources: list[dict[str, Any]] | None = None,
    confidence: float | str | None = None,
    warnings: list[Any] | None = None,
    missing_evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "agent_name": agent_name,
        "status": status,
        "content": content,
        "evidence_ids_used": evidence_ids_used or [],
        "sources": sources or [],
        "confidence": confidence,
        "warnings": warnings or [],
        "missing_evidence": missing_evidence or [],
    }


def _warning(
    code: str,
    domain: str,
    message: str,
    *,
    retryable: bool = False,
) -> StructuredWarning:
    return StructuredWarning(
        code=code,
        domain=domain,
        message=message,
        retryable=retryable,
        details={},
    )


def _evidence_domain(record: dict[str, Any]) -> str | None:
    if record.get("domain"):
        return str(record["domain"])
    source = record.get("source")
    if isinstance(source, dict) and source.get("domain"):
        return str(source["domain"])
    source_type = record.get("source_type")
    if source_type == "listing":
        return "property"
    if source_type == "project":
        return "project"
    if source_type == "market_metric":
        return "market"
    if source_type == "article":
        return "legal" if record.get("category") == "legal" else "news"
    if record.get("product_id") or record.get("price_text") or record.get("area_text"):
        return "property"
    return None


def _evidence_facts(record: dict[str, Any]) -> dict[str, Any]:
    facts = record.get("facts") or {}
    return facts if isinstance(facts, dict) else {}


def _evidence_id(record: dict[str, Any]) -> str | None:
    value = record.get("evidence_id")
    return str(value) if value else None


def _source_from_evidence(record: dict[str, Any], fallback_type: str) -> dict[str, Any]:
    source = record.get("source")
    if isinstance(source, dict):
        return source
    return _source_from_record(record, fallback_type)


def _sources_from_evidence(
    evidence: list[dict[str, Any]],
    fallback_type: str,
) -> list[dict[str, Any]]:
    return [_source_from_evidence(record, fallback_type) for record in evidence]


def _used_ids(evidence: list[dict[str, Any]]) -> list[str]:
    return [value for item in evidence if (value := _evidence_id(item))]


def _describe_evidence(record: dict[str, Any]) -> str:
    facts = _evidence_facts(record)
    if not facts:
        return _describe_record(record)

    title = facts.get("title") or "Nguon khong co tieu de"
    location = facts.get("location")
    if isinstance(location, dict):
        location_text = ", ".join(
            str(value)
            for value in (location.get("district"), location.get("city"))
            if value
        )
    else:
        location_text = str(location) if location else ""
    details = [
        str(title),
        location_text,
        str(facts.get("price_text") or ""),
        str(facts.get("area_text") or ""),
    ]
    return " - ".join(part for part in details if part)


async def run_property_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    property_evidence = [
        item for item in evidence if _evidence_domain(item) == "property"
    ]
    if not property_evidence:
        source_ready = _readiness_status(readiness, "listings") == "ready"
        content = (
            "Chua co bang chung listing phu hop de khang dinh bat dong san cu the. "
            "Toi chi co the goi y bo sung tieu chi tim kiem truoc khi so sanh."
            if source_ready
            else "Nguon listing chua san sang, nen toi chua co bang chung listing de khang dinh bat dong san cu the."
        )
        return _agent_result(
            agent_name="property_search",
            status="no_evidence",
            content=content,
            confidence="low",
            warnings=[
                _warning(
                    "no_listing_evidence"
                    if source_ready
                    else "listing_source_not_ready",
                    "property",
                    "No listing evidence was found."
                    if source_ready
                    else "Listing source is not ready.",
                )
            ],
            missing_evidence=["property"],
        )

    lines = [_describe_evidence(record) for record in property_evidence]
    content = (
        "Cac listing phu hop voi yeu cau:\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\nThong tin duoc rut ra tu nguon listing kem theo; can kiem tra lai tinh trang va gia truoc khi giao dich."
    )
    return _agent_result(
        agent_name="property_search",
        status="completed",
        content=content,
        evidence_ids_used=_used_ids(property_evidence),
        sources=_sources_from_evidence(property_evidence, "listing"),
        confidence="high",
    )


async def run_project_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    project_evidence = [item for item in evidence if _evidence_domain(item) == "project"]
    if not project_evidence:
        source_ready = _readiness_status(readiness, "projects") == "ready"
        warning = (
            "no_project_evidence" if source_ready else "project_source_not_ready"
        )
        content = (
            "Chua co bang chung du an de danh gia du an cu the. "
            "Toi se khong dua ra thong tin chi tiet neu chua co nguon kem theo."
            if source_ready
            else "Nguon du an chua san sang, nen toi chua co du bang chung de danh gia du an cu the."
        )
        return _agent_result(
            agent_name="project_agent",
            status="no_evidence",
            content=content,
            confidence="low",
            warnings=[_warning(warning, "project", content)],
            missing_evidence=["project"],
        )

    content = "Thong tin du an lien quan:\n" + "\n".join(
        f"- {_describe_evidence(record)}" for record in project_evidence
    )
    return _agent_result(
        agent_name="project_agent",
        status="completed",
        content=content,
        evidence_ids_used=_used_ids(project_evidence),
        sources=_sources_from_evidence(project_evidence, "project"),
        confidence="high",
    )


async def run_market_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    market_evidence = [item for item in evidence if _evidence_domain(item) == "market"]
    content = "Phan tich thi truong hien chi la snapshot tai thoi diem truy van, khong phai chuoi thoi gian day du."
    if market_evidence:
        content += "\nCac diem du lieu lien quan:\n" + "\n".join(
            f"- {_describe_evidence(record)}" for record in market_evidence
        )
    return _agent_result(
        agent_name="market_analysis",
        status="completed" if market_evidence else "no_evidence",
        content=content,
        evidence_ids_used=_used_ids(market_evidence),
        sources=_sources_from_evidence(market_evidence, "market_snapshot"),
        confidence="medium" if market_evidence else "low",
        warnings=[
            _warning(
                "market_snapshot_not_time_series",
                "market",
                "Market evidence is a current snapshot, not a full time series.",
            )
        ],
        missing_evidence=[] if market_evidence else ["market"],
    )


async def run_news_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    news_evidence = [item for item in evidence if _evidence_domain(item) == "news"]
    if not news_evidence:
        return _agent_result(
            agent_name="news_agent",
            status="no_evidence",
            content="Chua co bang chung tin tuc de tom tat cap nhat lien quan.",
            confidence="low",
            warnings=[
                _warning("no_news_evidence", "news", "No news evidence was found.")
            ],
            missing_evidence=["news"],
        )

    content = "Tin tuc lien quan:\n" + "\n".join(
        f"- {_describe_evidence(record)}" for record in news_evidence
    )
    return _agent_result(
        agent_name="news_agent",
        status="completed",
        content=content,
        evidence_ids_used=_used_ids(news_evidence),
        sources=_sources_from_evidence(news_evidence, "news_article"),
        confidence="high",
    )


async def run_legal_agent(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    legal_evidence = [item for item in evidence if _evidence_domain(item) == "legal"]
    if not legal_evidence:
        source_ready = _readiness_status(readiness, "legal") == "ready"
        content = (
            "Chua co bang chung phap ly de ket luan tinh trang phap ly. "
            "Thong tin phap ly do nguoi dang listing khai bao chi nen xem la thong tin chua xac minh. "
            "Vui long doi chieu van ban hien hanh hoac hoi chuyen gia phap ly truoc khi thuc hien."
            if source_ready
            else (
                "Kho tri thuc phap ly chua san sang, nen chua co bang chung phap ly de ket luan. "
                "Thong tin phap ly do nguoi dang listing khai bao chi nen xem la thong tin chua xac minh. "
                "Vui long doi chieu van ban hien hanh hoac hoi chuyen gia phap ly truoc khi thuc hien."
            )
        )
        return _agent_result(
            agent_name="legal_advisor",
            status="no_evidence",
            content=content,
            confidence="low",
            warnings=[
                _warning(
                    "insufficient_legal_evidence" if source_ready else "legal_kb_not_ready",
                    "legal",
                    "Legal evidence is missing."
                    if source_ready
                    else "Legal knowledge base is not ready.",
                )
            ],
            missing_evidence=["legal"],
        )

    content = (
        "Thong tin phap ly tham khao:\n"
        + "\n".join(f"- {_describe_evidence(record)}" for record in legal_evidence)
        + "\nNoi dung nay chi de tham khao, khong thay the tu van phap ly chuyen nghiep."
    )
    return _agent_result(
        agent_name="legal_advisor",
        status="completed",
        content=content,
        evidence_ids_used=_used_ids(legal_evidence),
        sources=_sources_from_evidence(legal_evidence, "legal_article"),
        confidence="high",
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

    property_evidence = [
        item for item in evidence if _evidence_domain(item) == "property"
    ]
    market_evidence = [item for item in evidence if _evidence_domain(item) == "market"]
    project_evidence = [item for item in evidence if _evidence_domain(item) == "project"]
    news_evidence = [item for item in evidence if _evidence_domain(item) == "news"]
    used_evidence = [
        *property_evidence,
        *market_evidence,
        *project_evidence,
        *news_evidence,
    ]

    warnings: list[StructuredWarning] = [
        _warning(
            "not_financial_advice",
            "market",
            "This is not financial advice.",
        )
    ]
    missing: list[str] = []
    status = "completed"
    if not market_evidence:
        warnings.append(
            _warning(
                "investment_market_data_missing",
                "market",
                "Market aggregate evidence is not available for this query.",
            )
        )
        missing.append("market")
        status = "partial" if property_evidence else "no_evidence"
    if not property_evidence:
        missing.append("property")
        status = "no_evidence"

    content = (
        f"Khau vi rui ro hien ghi nhan: {risk_value}. "
        "Nhan dinh dau tu nay khong phai loi khuyen tai chinh; can tu tham dinh dong tien, phap ly va kha nang vay."
    )
    if property_evidence:
        content += "\nBang chung listing lien quan:\n" + "\n".join(
            f"- {_describe_evidence(item)}" for item in property_evidence
        )
    if market_evidence:
        content += "\nDu lieu thi truong lien quan:\n" + "\n".join(
            f"- {_describe_evidence(item)}" for item in market_evidence
        )
    if project_evidence:
        content += "\nBang chung du an lien quan:\n" + "\n".join(
            f"- {_describe_evidence(item)}" for item in project_evidence
        )
    if news_evidence:
        content += "\nTin tuc lien quan:\n" + "\n".join(
            f"- {_describe_evidence(item)}" for item in news_evidence
        )

    return _agent_result(
        agent_name="investment_advisor",
        status=status,
        content=content,
        evidence_ids_used=_used_ids(used_evidence),
        sources=_sources_from_evidence(used_evidence, "investment_evidence"),
        confidence="medium" if used_evidence else "low",
        warnings=warnings,
        missing_evidence=missing,
    )
