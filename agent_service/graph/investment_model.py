from __future__ import annotations

from typing import Any, Literal

from agent_service.contracts import Evidence


Confidence = Literal["low", "medium", "high"]

DEFAULT_ASSUMPTIONS = {
    "equity_ratio": 0.4,
    "loan_ratio": 0.6,
    "interest_rate_annual": 0.1,
    "loan_term_years": 20,
    "vacancy_months_per_year": 1,
    "operating_cost_ratio": 0.08,
}


def _evidence_for_investment(
    *,
    evidence_by_id: dict[str, Evidence],
    evidence_for_agent: dict[str, list[str]],
) -> list[Evidence]:
    ids = evidence_for_agent.get("investment_advisor", [])
    if not ids:
        ids = list(evidence_by_id)
    return [evidence_by_id[evidence_id] for evidence_id in ids if evidence_id in evidence_by_id]


def _first_by_domain(evidence: list[Evidence], domain: str) -> list[Evidence]:
    return [item for item in evidence if item.domain == domain]


def _summary_from_evidence(items: list[Evidence]) -> dict[str, Any]:
    if not items:
        return {"evidence_ids": []}
    first = items[0]
    facts = dict(first.facts)
    facts["evidence_ids"] = [item.evidence_id for item in items]
    return facts


def build_investment_case(
    *,
    evidence_by_id: dict[str, Evidence],
    evidence_for_agent: dict[str, list[str]],
) -> dict[str, Any]:
    evidence = _evidence_for_investment(
        evidence_by_id=evidence_by_id,
        evidence_for_agent=evidence_for_agent,
    )
    property_items = _first_by_domain(evidence, "property")
    market_items = _first_by_domain(evidence, "market")
    legal_items = _first_by_domain(evidence, "legal")
    project_items = _first_by_domain(evidence, "project")
    news_items = _first_by_domain(evidence, "news")
    evidence_ids = [item.evidence_id for item in evidence]
    missing = []
    if not property_items:
        missing.append("property")
    if not market_items:
        missing.append("market")
    if not legal_items:
        missing.append("legal")
    return {
        "case_scope": "single_listing" if property_items else "area_screening",
        "target": _summary_from_evidence(property_items),
        "property_summary": _summary_from_evidence(property_items),
        "market_summary": _summary_from_evidence(market_items),
        "legal_summary": _summary_from_evidence(legal_items),
        "project_summary": _summary_from_evidence(project_items),
        "news_summary": _summary_from_evidence(news_items),
        "evidence_ids": evidence_ids,
        "missing_evidence": missing,
    }


def _preference_value(preferences: dict[str, Any], key: str) -> Any:
    value = preferences.get(key)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _assumption(
    *,
    value: Any,
    unit: str,
    source: str,
    depends_on: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    note: str = "",
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "source": source,
        "depends_on": depends_on or [],
        "evidence_ids": evidence_ids or [],
        "note": note,
    }


def _resolved_value(
    *,
    key: str,
    user_inputs: dict[str, Any],
    preferences: dict[str, Any],
    default: Any,
) -> tuple[Any, str]:
    if key in user_inputs and user_inputs[key] is not None:
        return user_inputs[key], "user"
    preference = _preference_value(preferences, key)
    if preference is not None:
        return preference, "preference"
    return default, "default"


def resolve_investment_assumptions(
    *,
    case: dict[str, Any],
    user_inputs: dict[str, Any],
    preferences: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    assumptions: dict[str, dict[str, Any]] = {}
    property_summary = case.get("property_summary") or {}
    property_evidence_ids = list(property_summary.get("evidence_ids") or [])
    price = property_summary.get("price")
    area = property_summary.get("area")
    if price is not None:
        assumptions["purchase_price"] = _assumption(
            value=price,
            unit="billion_vnd",
            source="derived",
            depends_on=property_evidence_ids,
            evidence_ids=property_evidence_ids,
            note="Purchase price derived from listing evidence.",
        )
    if area is not None:
        assumptions["area"] = _assumption(
            value=area,
            unit="m2",
            source="derived",
            depends_on=property_evidence_ids,
            evidence_ids=property_evidence_ids,
            note="Area derived from listing evidence.",
        )

    ratio_keys = {"equity_ratio", "loan_ratio", "interest_rate_annual", "operating_cost_ratio"}
    for key, default in DEFAULT_ASSUMPTIONS.items():
        value, source = _resolved_value(
            key=key,
            user_inputs=user_inputs,
            preferences=preferences,
            default=default,
        )
        unit = "ratio_0_1" if key in ratio_keys else "years" if key == "loan_term_years" else "months"
        assumptions[key] = _assumption(
            value=value,
            unit=unit,
            source=source,
            note=f"{key} resolved from {source}.",
        )

    rent_value, rent_source = _resolved_value(
        key="expected_monthly_rent",
        user_inputs=user_inputs,
        preferences=preferences,
        default=None,
    )
    assumptions["expected_monthly_rent"] = _assumption(
        value=rent_value,
        unit="vnd_per_month",
        source=rent_source if rent_value is not None else "default",
        note=(
            "Expected monthly rent provided by user or preference."
            if rent_value is not None
            else "Expected monthly rent is missing and needs confirmation."
        ),
    )
    return assumptions
