from __future__ import annotations

from typing import Any


def _perspective(
    *,
    role: str,
    stance: str,
    summary: str,
    evidence_ids: list[str],
    depends_on: list[str],
    confidence: str,
    risk_level: str,
    suggested_actions: list[str],
) -> dict[str, Any]:
    return {
        "role": role,
        "stance": stance,
        "summary": summary,
        "claims": [
            {
                "type": "analysis",
                "text": summary,
                "evidence_ids": evidence_ids,
            }
        ]
        if evidence_ids
        else [{"type": "missing_evidence", "text": summary, "evidence_ids": []}],
        "evidence_ids": evidence_ids,
        "depends_on": depends_on,
        "confidence": confidence,
        "risk_level": risk_level,
        "suggested_actions": suggested_actions,
    }


def _metric_value(metrics: dict[str, Any], key: str) -> Any:
    metric = metrics.get(key) or {}
    return metric.get("value")


def _default_or_estimated_keys(assumptions: dict[str, dict[str, Any]]) -> list[str]:
    return [
        key
        for key, assumption in assumptions.items()
        if assumption.get("source") in {"default", "estimated"}
    ]


def build_committee_review(
    *,
    investment_case: dict[str, Any],
    investment_assumptions: dict[str, dict[str, Any]],
    investment_metrics: dict[str, dict[str, Any]],
    agent_blackboard: dict[str, Any],
    warnings: list[Any],
) -> dict[str, Any]:
    del agent_blackboard
    del warnings
    missing_evidence = list(investment_case.get("missing_evidence") or [])
    property_ids = list(
        (investment_case.get("property_summary") or {}).get("evidence_ids") or []
    )
    market_ids = list(
        (investment_case.get("market_summary") or {}).get("evidence_ids") or []
    )
    legal_ids = list(
        (investment_case.get("legal_summary") or {}).get("evidence_ids") or []
    )
    metric_warnings = list(
        (investment_metrics.get("metric_warnings") or {}).get("warnings") or []
    )
    default_or_estimated = _default_or_estimated_keys(investment_assumptions)
    required_confirmations: list[str] = []
    if "missing_expected_monthly_rent" in metric_warnings:
        required_confirmations.append("expected_monthly_rent")
    if "market" in missing_evidence:
        required_confirmations.append("market_benchmark")
    if "legal" in missing_evidence:
        required_confirmations.append("legal_documents")

    net_yield = _metric_value(investment_metrics, "net_yield")
    monthly_cashflow = _metric_value(investment_metrics, "monthly_cashflow_estimate")
    bull_summary = (
        "Co the xem xet neu gia/m2 va dong tien dap ung nguong cua nha dau tu."
        if net_yield is not None
        else "Chua du du lieu dong tien de lap bull case manh."
    )
    bear_summary = (
        "Dong tien uoc tinh am hoac phu thuoc nhieu vao gia dinh can xac nhan."
        if monthly_cashflow is None or monthly_cashflow < 0
        else "Rui ro chinh nam o tinh thanh khoan, phap ly va sai lech gia dinh."
    )
    perspectives = [
        _perspective(
            role="bull",
            stance="positive" if net_yield is not None else "unknown",
            summary=bull_summary,
            evidence_ids=property_ids + market_ids,
            depends_on=["net_yield", "price_per_m2"],
            confidence="medium" if net_yield is not None else "low",
            risk_level="medium",
            suggested_actions=[
                "Xac nhan tien thue ky vong",
                "So sanh them listing cung khu vuc",
            ],
        ),
        _perspective(
            role="bear",
            stance="negative",
            summary=bear_summary,
            evidence_ids=property_ids,
            depends_on=["monthly_cashflow_estimate", *default_or_estimated],
            confidence="medium",
            risk_level="medium" if monthly_cashflow is not None else "high",
            suggested_actions=[
                "Kiem tra lai gia mua",
                "Tinh kich ban lai suat cao hon",
            ],
        ),
        _perspective(
            role="legal_risk",
            stance="unknown" if "legal" in missing_evidence else "neutral",
            summary=(
                "Chua co bang chung phap ly, can kiem tra so hong, quy hoach va tranh chap."
                if "legal" in missing_evidence
                else "Co bang chung phap ly lien quan nhung van can doi chieu tai lieu goc."
            ),
            evidence_ids=legal_ids,
            depends_on=legal_ids,
            confidence="low" if "legal" in missing_evidence else "medium",
            risk_level="unknown" if "legal" in missing_evidence else "medium",
            suggested_actions=[
                "Kiem tra so hong",
                "Kiem tra quy hoach",
                "Hoi chuyen gia phap ly",
            ],
        ),
        _perspective(
            role="market_risk",
            stance="unknown" if "market" in missing_evidence else "neutral",
            summary=(
                "Chua co benchmark thi truong khu vuc nen khong the ket luan gia mua hap dan."
                if "market" in missing_evidence
                else "Da co benchmark thi truong de so sanh gia/m2."
            ),
            evidence_ids=market_ids,
            depends_on=["market_price_delta", *market_ids],
            confidence="low" if "market" in missing_evidence else "medium",
            risk_level="unknown" if "market" in missing_evidence else "medium",
            suggested_actions=[
                "Lay them benchmark gia/m2",
                "So sanh lich su giao dich khu vuc",
            ],
        ),
        _perspective(
            role="finance",
            stance="negative"
            if monthly_cashflow is not None and monthly_cashflow < 0
            else "neutral",
            summary="Mo hinh tai chinh dang dua tren cac gia dinh can xac nhan.",
            evidence_ids=property_ids,
            depends_on=list(investment_metrics),
            confidence="medium"
            if "expected_monthly_rent" not in required_confirmations
            else "low",
            risk_level="medium",
            suggested_actions=[
                "Xac nhan lai suat vay",
                "Xac nhan ty le vay",
                "Xac nhan tien thue",
            ],
        ),
        _perspective(
            role="missing_inputs",
            stance="unknown" if required_confirmations else "neutral",
            summary=(
                "Can xac nhan: " + ", ".join(required_confirmations)
                if required_confirmations
                else "Cac input cot loi da co du cho sang loc ban dau."
            ),
            evidence_ids=[],
            depends_on=required_confirmations,
            confidence="high",
            risk_level="high" if required_confirmations else "low",
            suggested_actions=required_confirmations,
        ),
    ]
    if required_confirmations:
        decision = "need_more_info"
        confidence = "low"
    elif monthly_cashflow is not None and monthly_cashflow < 0:
        decision = "wait"
        confidence = "medium"
    else:
        decision = "consider"
        confidence = "medium" if default_or_estimated else "high"
    if decision == "consider" and confidence == "high" and default_or_estimated:
        confidence = "medium"
    return {
        "perspectives": perspectives,
        "recommendation": {
            "decision": decision,
            "confidence": confidence,
            "rationale": (
                "Recommendation derived from financial metrics, missing inputs, "
                "and evidence availability."
            ),
            "required_confirmations": list(dict.fromkeys(required_confirmations)),
        },
    }
