from __future__ import annotations

import re
import unicodedata
from statistics import mean
from typing import Any

from agent_service.contracts import StructuredWarning


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    stripped = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return stripped.replace("đ", "d").replace("Đ", "D").lower()


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

    # ── Compute price/m² and ranking ──────────────────────────────────
    listings_with_price = _extract_listing_prices(property_evidence)
    comparisons = _compare_with_market(listings_with_price, preferences)

    content = "🏠 **Kết quả tìm kiếm bất động sản:**\n\n"
    for i, listing in enumerate(comparisons[:10], 1):
        content += _format_listing_card(i, listing)

    if comparisons:
        content += (
            "\n> ℹ️ Giá/m² tính từ diện tích và giá listing. "
            "Giá thực tế có thể thay đổi khi thương lượng. "
            "Nên kiểm tra trực tiếp và xác minh pháp lý trước khi giao dịch."
        )
    else:
        content += "\n".join(f"- {line}" for line in lines)
        content += "\nThong tin duoc rut ra tu nguon listing kem theo."

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

    # ── 1. Extract timeseries from evidence facts ──────────────────────
    timeseries = _extract_timeseries_from_evidence(market_evidence)

    # ── 2. Analyze trend (user's reference logic, adapted) ─────────────
    trend = analyze_market_evidence(timeseries) if timeseries else None

    # ── 3. Build response ──────────────────────────────────────────────
    warnings: list[Any] = []
    if not timeseries:
        warnings.append(
            _warning(
                "market_no_timeseries",
                "market",
                "Không có dữ liệu chuỗi thời gian cho khu vực/loại hình này.",
            )
        )

    if not market_evidence and not timeseries:
        source_ready = _readiness_status(readiness, "market_snapshots") == "ready"
        return _agent_result(
            agent_name="market_analysis",
            status="no_evidence",
            content=(
                "Chưa có dữ liệu thị trường cho khu vực này. "
                "Vui lòng thử khu vực khác hoặc quay lại sau khi dữ liệu được cập nhật."
            ),
            confidence="low",
            warnings=[
                _warning(
                    "market_no_data" if source_ready else "market_source_not_ready",
                    "market",
                    "No market data found for this segment.",
                )
            ],
            missing_evidence=["market"],
        )

    content = _format_timeseries_response(timeseries, trend, market_evidence)

    # Build chart data for frontend rendering
    chart = _build_timeseries_chart(timeseries, trend) if timeseries else None

    result = _agent_result(
        agent_name="market_analysis",
        status="completed",
        content=content,
        evidence_ids_used=_used_ids(market_evidence),
        sources=_sources_from_evidence(market_evidence, "market_snapshot"),
        confidence="high" if trend else "medium",
        warnings=warnings if warnings else None,
    )
    if chart:
        result["chart"] = chart
    return result


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

    content = _format_legal_response(legal_evidence, query)
    return _agent_result(
        agent_name="legal_advisor",
        status="completed",
        content=content,
        evidence_ids_used=_used_ids(legal_evidence),
        sources=_sources_from_evidence(legal_evidence, "legal_article"),
        confidence="high",
    )


# ── Market Agent helpers ──────────────────────────────────────────────────

def _extract_timeseries_from_evidence(
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract timeseries data from market evidence facts.

    Evidence records from ``lookup_market_timeseries`` contain facts with
    snapshot_month, avg_price_per_m2, median_price_per_m2, etc.
    """
    rows: list[dict[str, Any]] = []
    for item in evidence:
        facts = _evidence_facts(item)
        if facts.get("snapshot_month"):
            rows.append(facts)
    return rows


def analyze_market_evidence(
    market_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Analyze timeseries evidence for trend, change %, and volatility.

    Adapted from the project's reference implementation.  Expects evidence
    dicts with at least ``snapshot_month`` and ``median_price_per_m2``.
    """
    sorted_data = sorted(
        market_evidence,
        key=lambda x: x.get("snapshot_month") or "",
    )

    if len(sorted_data) < 2:
        return {
            "trend": "unknown",
            "change_percent": None,
            "confidence": "low",
            "warnings": [
                _warning(
                    "insufficient_time_series",
                    "market",
                    "Need at least two market snapshots to compute trend.",
                )
            ],
            "missing_evidence": ["time_series"],
        }

    first = sorted_data[0]
    last = sorted_data[-1]

    first_price = first.get("median_price_per_m2") or first.get("avg_price_per_m2")
    last_price = last.get("median_price_per_m2") or last.get("avg_price_per_m2")

    if not first_price or not last_price:
        return {
            "trend": "unknown",
            "change_percent": None,
            "confidence": "low",
            "warnings": [
                _warning(
                    "missing_price_per_m2",
                    "market",
                    "Market snapshots do not contain enough price_per_m2 data.",
                )
            ],
            "missing_evidence": ["median_price_per_m2"],
        }

    change_percent = ((last_price - first_price) / first_price) * 100

    if change_percent > 3:
        trend = "increasing"
    elif change_percent < -3:
        trend = "decreasing"
    else:
        trend = "stable"

    # Compute additional metrics
    prices = [r.get("median_price_per_m2") or r.get("avg_price_per_m2", 0) for r in sorted_data]
    prices = [p for p in prices if p]

    return {
        "trend": trend,
        "change_percent": round(change_percent, 2),
        "first_price": first_price,
        "last_price": last_price,
        "first_month": first.get("snapshot_month"),
        "last_month": last.get("snapshot_month"),
        "min_price": round(min(prices), 2) if prices else None,
        "max_price": round(max(prices), 2) if prices else None,
        "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
        "data_points": len(sorted_data),
        "total_listings": sum(r.get("listing_count", 0) for r in sorted_data),
        "confidence": "medium",
    }


def _format_timeseries_response(
    timeseries: list[dict[str, Any]],
    trend: dict[str, Any] | None,
    evidence: list[dict[str, Any]],
) -> str:
    """Format market timeseries analysis as Vietnamese text."""
    lines = ["📊 **Phân tích thị trường**\n"]

    if trend and trend["trend"] != "unknown":
        arrow = "📈" if trend["trend"] == "increasing" else "📉" if trend["trend"] == "decreasing" else "➡️"
        trend_label = {
            "increasing": "tăng", "decreasing": "giảm", "stable": "đi ngang",
        }.get(trend["trend"], trend["trend"])

        lines.append(
            f"{arrow} Xu hướng: **{trend_label}** "
            f"({trend['change_percent']:+.2f}% từ {trend.get('first_month', '?')} đến {trend.get('last_month', '?')})"
        )
        if trend.get("avg_price"):
            lines.append(f"- Giá trung bình: **{trend['avg_price']:,.0f} triệu/m²**")
        if trend.get("min_price") and trend.get("max_price"):
            lines.append(f"- Khoảng giá: {trend['min_price']:,.0f} → {trend['max_price']:,.0f} triệu/m²")
        if trend.get("total_listings"):
            lines.append(f"- Tổng số tin: {trend['total_listings']:,} ({trend.get('data_points', 0)} tháng)")
        lines.append(f"- Độ tin cậy: {trend.get('confidence', 'medium')}")
    else:
        lines.append("⚠️ Chưa đủ dữ liệu chuỗi thời gian để phân tích xu hướng.")

    if evidence:
        lines.append("\n📋 **Dữ liệu hiện tại:**")
        for record in evidence[:5]:
            lines.append(f"- {_describe_evidence(record)}")

    lines.append(
        "\n> ℹ️ Dữ liệu từ thị trường, chỉ mang tính tham khảo. "
        "Giá thực tế có thể khác tùy vị trí cụ thể."
    )
    return "\n".join(lines)


def _build_timeseries_chart(
    timeseries: list[dict[str, Any]],
    trend: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build chart data payload for frontend rendering.

    Returns a dict compatible with Chart.js / Recharts line chart.
    """
    if len(timeseries) < 2:
        return None

    labels = [r.get("snapshot_month", "") for r in timeseries]
    prices = [r.get("avg_price_per_m2") or r.get("median_price_per_m2") for r in timeseries]
    counts = [r.get("listing_count", 0) for r in timeseries]

    return {
        "type": "line",
        "title": "Biến động giá bất động sản theo thời gian",
        "x_axis": {
            "label": "Tháng",
            "values": labels,
        },
        "series": [
            {
                "name": "Giá trung bình (triệu/m²)",
                "values": [round(p, 2) if p else None for p in prices],
                "color": "#2563eb",
                "y_axis": "left",
            },
            {
                "name": "Số lượng tin đăng",
                "values": counts,
                "color": "#16a34a",
                "y_axis": "right",
            },
        ],
        "trend": {
            "direction": trend.get("trend", "unknown") if trend else "unknown",
            "change_percent": trend.get("change_percent") if trend else None,
        } if trend else None,
    }


# ── Property Agent helpers ────────────────────────────────────────────────

def _extract_listing_prices(
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract price and area from listing evidence for comparison."""
    results: list[dict[str, Any]] = []
    for item in evidence:
        facts = _evidence_facts(item)
        price = _number(facts.get("price") or facts.get("price_vnd"))
        area = _number(facts.get("area") or facts.get("area_m2"))
        price_text = facts.get("price_text", "")
        area_text = facts.get("area_text", "")

        # Parse Vietnamese price text: "2.5 tỷ" → 2500, "1.2 triệu/tháng" → 1.2
        if price is None and price_text:
            price = _parse_vnd_price(price_text)
        if area is None and area_text:
            area = _parse_area(area_text)

        title = facts.get("title") or item.get("title") or "N/A"
        location = _record_location(item) or ""

        price_per_m2 = round(price / area, 2) if price and area and area > 0 else None

        results.append({
            "title": title,
            "location": location,
            "price": price,
            "area": area,
            "price_text": price_text,
            "area_text": area_text,
            "price_per_m2": price_per_m2,
            "product_id": item.get("product_id") or item.get("id"),
            "url": item.get("url") or "",
        })
    return results


def _parse_vnd_price(text: str) -> float | None:
    """Parse Vietnamese price text to millions VND. Handles '1.6 tỷ', '2,5 tỷ', '800 triệu', etc."""
    text = text.lower().strip().replace("~", "").replace("khoảng", "").replace("khoang", "")
    # "1,6 tỷ" or "1.6 tỷ" or "1 tỷ 6"
    match = re.search(r"([\d,.]+)\s*(tỷ|ty|tỉ|ti|triệu|trieu|nghìn|ngan|tr)", text)
    if not match:
        # Fallback: just a number
        match = re.search(r"([\d,.]+)", text)
        if match:
            val = float(match.group(1).replace(",", "."))
            return val * 1000 if val < 100 else val
        return None
    value = float(match.group(1).replace(",", "."))
    unit = match.group(2)
    if unit in ("tỷ", "ty", "tỉ", "ti"):
        return value * 1000
    elif unit in ("triệu", "trieu"):
        return value
    elif unit in ("nghìn", "ngan", "tr"):
        return value / 1000
    return value * 1000 if value < 100 else value


def _parse_area(text: str) -> float | None:
    """Parse Vietnamese area text to m²."""
    match = re.search(r"([\d,.]+)\s*(m2|m²|m)", text.lower())
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def _compare_with_market(
    listings: list[dict[str, Any]],
    preferences: dict[str, Any],
) -> list[dict[str, Any]]:
    """Rank listings and add market comparison tags."""
    # Sort by price_per_m2 if available
    with_price = [l for l in listings if l["price_per_m2"]]
    without_price = [l for l in listings if not l["price_per_m2"]]

    with_price.sort(key=lambda x: x["price_per_m2"] or 0)

    # Add comparison tags
    all_prices = [l["price_per_m2"] for l in with_price if l["price_per_m2"]]
    avg_price = mean(all_prices) if all_prices else None

    for listing in with_price:
        if avg_price and listing["price_per_m2"]:
            delta = ((listing["price_per_m2"] - avg_price) / avg_price) * 100
            if delta < -10:
                listing["tag"] = "💰 Rẻ hơn TB khu vực"
            elif delta > 10:
                listing["tag"] = "📌 Cao hơn TB khu vực"
            else:
                listing["tag"] = "✅ Giá ngang TB khu vực"
            listing["delta_pct"] = round(delta, 1)
        else:
            listing["tag"] = ""

    return with_price + without_price


def _format_listing_card(index: int, listing: dict[str, Any]) -> str:
    """Format a single listing as a rich card."""
    lines = [f"**{index}. {listing['title']}**"]
    if listing.get("location"):
        lines.append(f"   📍 {listing['location']}")
    if listing.get("price_text"):
        lines.append(f"   💵 {listing['price_text']}")
    if listing.get("area_text"):
        lines.append(f"   📐 {listing['area_text']}")
    if listing.get("price_per_m2"):
        lines.append(f"   📊 {listing['price_per_m2']:,.0f} triệu/m²")
    if listing.get("tag"):
        lines.append(f"   {listing['tag']}")
    if listing.get("url"):
        lines.append(f"   🔗 {listing['url']}")
    return "\n".join(lines)


# ── Legal Agent helpers ───────────────────────────────────────────────────

def _format_legal_response(
    evidence: list[dict[str, Any]],
    query: str,
) -> str:
    """Format legal advice with citations and validity check."""
    lines = ["⚖️ **Thông tin pháp lý tham khảo:**\n"]

    for i, record in enumerate(evidence[:8], 1):
        facts = _evidence_facts(record)
        source = record.get("source", {})
        title = facts.get("title") or source.get("title") or record.get("title") or f"Văn bản #{i}"
        citation = facts.get("citation") or record.get("citation") or ""
        text = facts.get("text") or record.get("text") or _describe_evidence(record)

        # Build citation reference
        cit_parts = []
        if isinstance(citation, dict):
            chuong = citation.get("chuong", "")
            dieu = citation.get("dieu_number", "") or citation.get("dieu", "")
            khoan = citation.get("khoan_number", "") or citation.get("khoan", "")
            if chuong:
                cit_parts.append(f"Chương {chuong}")
            if dieu:
                cit_parts.append(f"Điều {dieu}")
            if khoan:
                cit_parts.append(f"Khoản {khoan}")
        cit_ref = ", ".join(cit_parts) if cit_parts else ""

        lines.append(f"**{i}. {title}**")
        if cit_ref:
            lines.append(f"   📖 {cit_ref}")
        lines.append(f"   {text[:300]}{'...' if len(text) > 300 else ''}")

        # Validity check from metadata
        metadata = record.get("metadata_json") or record.get("metadata") or {}
        ngay_hh = metadata.get("hf_ngay_ban_hanh") or metadata.get("ngay_ban_hanh") or ""
        if ngay_hh:
            lines.append(f"   📅 Ban hành: {ngay_hh}")

        lines.append("")

    lines.append(
        "---\n"
        "> ⚠️ **Lưu ý quan trọng:**\n"
        "> - Thông tin trên chỉ mang tính tham khảo, không thay thế tư vấn pháp lý chuyên nghiệp\n"
        "> - Văn bản pháp luật có thể đã được sửa đổi, bổ sung\n"
        "> - Cần đối chiếu với văn bản hiện hành trước khi áp dụng\n"
        "> - Nên tham khảo ý kiến luật sư hoặc chuyên gia pháp lý cho trường hợp cụ thể"
    )
    return "\n".join(lines)


# ── Investment helpers ────────────────────────────────────────────────────

def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _market_avg_price_per_m2(market_evidence: list[dict[str, Any]]) -> float | None:
    for item in market_evidence:
        facts = _evidence_facts(item)
        if facts.get("metric") == "avg_price_per_m2":
            return _number(facts.get("value"))
    return None


def _investment_calculations(
    *,
    property_evidence: list[dict[str, Any]],
    market_evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    market_avg = _market_avg_price_per_m2(market_evidence)
    calculations: list[dict[str, Any]] = []
    for item in property_evidence:
        facts = _evidence_facts(item)
        price_billion = _number(facts.get("price"))
        area_m2 = _number(facts.get("area"))
        if price_billion is None or area_m2 in {None, 0}:
            continue
        listing_price_per_m2 = round(price_billion * 1000 / area_m2, 2)
        calculation = {
            "title": facts.get("title") or "Listing",
            "listing_price_per_m2_million": listing_price_per_m2,
        }
        if market_avg not in {None, 0}:
            calculation["market_avg_price_per_m2_million"] = market_avg
            calculation["market_delta_percent"] = round(
                ((listing_price_per_m2 - market_avg) / market_avg) * 100,
                2,
            )
        calculations.append(calculation)
    return calculations


def _estimate_roi(
    calculations: list[dict[str, Any]],
    market_evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Estimate ROI attractiveness for each listing."""
    results = []
    for calc in calculations:
        price_m2 = calc.get("listing_price_per_m2_million", 0)
        delta = calc.get("market_delta_percent")

        # Attractiveness: lower delta = better buy (below market)
        if delta is not None:
            if delta < -15:
                score = 9
                trend = "up"
                label = "Rất hấp dẫn (thấp hơn TB)"
            elif delta < -5:
                score = 7
                trend = "up"
                label = "Hấp dẫn (dưới giá TB)"
            elif delta < 5:
                score = 6
                trend = "flat"
                label = "Giá hợp lý (ngang TB)"
            elif delta < 15:
                score = 4
                trend = "down"
                label = "Cao hơn TB, cân nhắc"
            else:
                score = 2
                trend = "down"
                label = "Đắt hơn nhiều so với TB"
        else:
            score = 5
            trend = "flat"
            label = "Chưa đủ dữ liệu so sánh"

        results.append({
            "title": calc.get("title", "N/A"),
            "price_per_m2": price_m2,
            "delta_pct": delta,
            "attractiveness_score": score,
            "trend": trend,
            "trend_label": label,
        })
    return results


def _assess_risk(
    calculations: list[dict[str, Any]],
    market_evidence: list[dict[str, Any]],
    news_evidence: list[dict[str, Any]],
) -> str:
    """Assess investment risk based on available data."""
    risks = []

    # Market data risk
    if not market_evidence:
        risks.append("⚠️ Thiếu dữ liệu thị trường để so sánh — rủi ro thông tin cao")

    # Price volatility risk
    high_delta = [c for c in calculations if c.get("market_delta_percent") and abs(c["market_delta_percent"]) > 20]
    if high_delta:
        risks.append(f"📊 {len(high_delta)} listing có giá chênh lệch >20% so với TB khu vực")

    # Legal risk
    risks.append("⚖️ Cần kiểm tra pháp lý: sổ đỏ, quy hoạch, tranh chấp")

    # Market liquidity
    risks.append("💧 Rủi ro thanh khoản: BĐS không dễ bán nhanh như chứng khoán")

    if news_evidence:
        risks.append("📰 Có tin tức liên quan — cần đánh giá tác động thị trường")

    return "\n".join(f"- {r}" for r in risks)

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

    calculations = _investment_calculations(
        property_evidence=property_evidence,
        market_evidence=market_evidence,
    )

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
    if calculations:
        rois = _estimate_roi(calculations, market_evidence)
        content += "\n💰 **Ước tính đầu tư:**\n" + "\n".join(
            f"- {r['title']}: Giá {r['price_per_m2']} tr/m² | "
            f"{'📈' if r.get('trend','') == 'up' else '📉' if r.get('trend','') == 'down' else '➡️'} "
            f"Xu hướng {r.get('trend_label','chưa rõ')} | "
            f"Điểm hấp dẫn: {r.get('attractiveness_score','?')}/10"
            for r in rois[:5]
        )
        risk = _assess_risk(calculations, market_evidence, news_evidence)
        content += f"\n\n⚠️ **Đánh giá rủi ro:**\n{risk}"

        content += (
            "\n\n> ⚠️ Đây KHÔNG phải lời khuyên tài chính. "
            "Cần tự thẩm định dòng tiền, pháp lý và khả năng vay trước khi đầu tư."
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


