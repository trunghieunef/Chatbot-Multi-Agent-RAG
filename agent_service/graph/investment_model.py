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
    if "investment_advisor" in evidence_for_agent:
        ids = evidence_for_agent["investment_advisor"]
    else:
        ids = list(evidence_by_id)
    return [evidence_by_id[evidence_id] for evidence_id in ids if evidence_id in evidence_by_id]


def _first_by_domain(evidence: list[Evidence], domain: str) -> list[Evidence]:
    return [item for item in evidence if item.domain == domain]


def _summary_from_evidence(items: list[Evidence]) -> dict[str, Any]:
    if not items:
        return {"evidence_ids": [], "items": []}
    first = items[0]
    facts = dict(first.facts)
    facts["evidence_ids"] = [item.evidence_id for item in items]
    facts["primary_evidence_id"] = first.evidence_id
    facts["primary_evidence_ids"] = [first.evidence_id]
    facts["items"] = [
        {
            "evidence_id": item.evidence_id,
            "facts": dict(item.facts),
            "source_type": item.source_type,
        }
        for item in items
    ]
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


def _has_explicit_value(
    *,
    key: str,
    user_inputs: dict[str, Any],
    preferences: dict[str, Any],
) -> bool:
    return (
        (key in user_inputs and user_inputs[key] is not None)
        or _preference_value(preferences, key) is not None
    )


def _capital_stack_note(equity_ratio: Any, loan_ratio: Any) -> str:
    if not isinstance(equity_ratio, int | float) or not isinstance(loan_ratio, int | float):
        return ""
    if abs((equity_ratio + loan_ratio) - 1.0) <= 0.000001:
        return ""
    return "Capital stack does not sum to 1.0; please confirm."


def _ratio_complement(value: Any) -> float | None:
    if not isinstance(value, int | float):
        return None
    return round(1 - value, 10)


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

    ratio_keys = {"interest_rate_annual", "operating_cost_ratio"}
    for key, default in DEFAULT_ASSUMPTIONS.items():
        if key in {"equity_ratio", "loan_ratio"}:
            continue
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

    loan_is_explicit = _has_explicit_value(
        key="loan_ratio",
        user_inputs=user_inputs,
        preferences=preferences,
    )
    equity_is_explicit = _has_explicit_value(
        key="equity_ratio",
        user_inputs=user_inputs,
        preferences=preferences,
    )
    if loan_is_explicit and not equity_is_explicit:
        loan_value, loan_source = _resolved_value(
            key="loan_ratio",
            user_inputs=user_inputs,
            preferences=preferences,
            default=DEFAULT_ASSUMPTIONS["loan_ratio"],
        )
        assumptions["loan_ratio"] = _assumption(
            value=loan_value,
            unit="ratio_0_1",
            source=loan_source,
            note=f"loan_ratio resolved from {loan_source}.",
        )
        assumptions["equity_ratio"] = _assumption(
            value=_ratio_complement(loan_value),
            unit="ratio_0_1",
            source="derived",
            depends_on=["loan_ratio"],
            note="equity_ratio derived from loan_ratio.",
        )
    elif equity_is_explicit and not loan_is_explicit:
        equity_value, equity_source = _resolved_value(
            key="equity_ratio",
            user_inputs=user_inputs,
            preferences=preferences,
            default=DEFAULT_ASSUMPTIONS["equity_ratio"],
        )
        assumptions["equity_ratio"] = _assumption(
            value=equity_value,
            unit="ratio_0_1",
            source=equity_source,
            note=f"equity_ratio resolved from {equity_source}.",
        )
        assumptions["loan_ratio"] = _assumption(
            value=_ratio_complement(equity_value),
            unit="ratio_0_1",
            source="derived",
            depends_on=["equity_ratio"],
            note="loan_ratio derived from equity_ratio.",
        )
    else:
        equity_value, equity_source = _resolved_value(
            key="equity_ratio",
            user_inputs=user_inputs,
            preferences=preferences,
            default=DEFAULT_ASSUMPTIONS["equity_ratio"],
        )
        loan_value, loan_source = _resolved_value(
            key="loan_ratio",
            user_inputs=user_inputs,
            preferences=preferences,
            default=DEFAULT_ASSUMPTIONS["loan_ratio"],
        )
        note = _capital_stack_note(equity_value, loan_value)
        assumptions["equity_ratio"] = _assumption(
            value=equity_value,
            unit="ratio_0_1",
            source=equity_source,
            note=note or f"equity_ratio resolved from {equity_source}.",
        )
        assumptions["loan_ratio"] = _assumption(
            value=loan_value,
            unit="ratio_0_1",
            source=loan_source,
            note=note or f"loan_ratio resolved from {loan_source}.",
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


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric(
    *,
    value: Any,
    unit: str,
    depends_on: list[str],
    formula: str,
    confidence: Confidence,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "depends_on": depends_on,
        "formula": formula,
        "confidence": confidence,
        "warnings": warnings or [],
    }


def _monthly_payment_billion(
    *,
    principal_billion: float,
    annual_rate: float,
    years: float,
) -> float | None:
    months = int(years * 12)
    if principal_billion <= 0 or months <= 0:
        return None
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        return round(principal_billion / months, 4)
    payment = principal_billion * (
        monthly_rate * (1 + monthly_rate) ** months
    ) / ((1 + monthly_rate) ** months - 1)
    return round(payment, 4)


def _market_primary_evidence_ids(market_summary: dict[str, Any]) -> list[str]:
    primary_ids = market_summary.get("primary_evidence_ids")
    if primary_ids:
        return list(primary_ids)
    primary_id = market_summary.get("primary_evidence_id")
    if primary_id:
        return [str(primary_id)]
    return list(market_summary.get("evidence_ids") or [])


def calculate_investment_metrics(
    *,
    case: dict[str, Any],
    assumptions: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    purchase_price = _number((assumptions.get("purchase_price") or {}).get("value"))
    area = _number((assumptions.get("area") or {}).get("value"))
    loan_ratio = _number((assumptions.get("loan_ratio") or {}).get("value")) or 0.0
    interest_rate = (
        _number((assumptions.get("interest_rate_annual") or {}).get("value")) or 0.0
    )
    loan_term_years = (
        _number((assumptions.get("loan_term_years") or {}).get("value")) or 0.0
    )
    rent_vnd = _number((assumptions.get("expected_monthly_rent") or {}).get("value"))
    vacancy_months = _number((assumptions.get("vacancy_months_per_year") or {}).get("value")) or 0.0
    operating_cost_ratio = (
        _number((assumptions.get("operating_cost_ratio") or {}).get("value")) or 0.0
    )

    if purchase_price is None:
        warnings.append("missing_purchase_price")
    if area is None:
        warnings.append("missing_area")
    if rent_vnd is None:
        warnings.append("missing_expected_monthly_rent")

    if purchase_price is not None and area not in {None, 0}:
        price_per_m2 = round(purchase_price * 1000 / area, 2)
        metrics["price_per_m2"] = _metric(
            value=price_per_m2,
            unit="million_vnd_per_m2",
            depends_on=["purchase_price", "area"],
            formula="purchase_price_billion_vnd * 1000 / area_m2",
            confidence="high",
        )
        market_summary = case.get("market_summary") or {}
        market_avg = _number(market_summary.get("value"))
        if market_avg not in {None, 0}:
            metrics["market_price_delta"] = _metric(
                value=round((price_per_m2 - market_avg) / market_avg, 4),
                unit="ratio_0_1",
                depends_on=["price_per_m2", *_market_primary_evidence_ids(market_summary)],
                formula="(price_per_m2 - market_avg_price_per_m2) / market_avg_price_per_m2",
                confidence="medium",
            )

    if purchase_price is not None:
        loan_amount = round(purchase_price * loan_ratio, 4)
        metrics["loan_amount"] = _metric(
            value=loan_amount,
            unit="billion_vnd",
            depends_on=["purchase_price", "loan_ratio"],
            formula="purchase_price * loan_ratio",
            confidence="medium",
            warnings=["uses_default_loan_ratio"]
            if (assumptions.get("loan_ratio") or {}).get("source") == "default"
            else [],
        )
        monthly_payment = _monthly_payment_billion(
            principal_billion=loan_amount,
            annual_rate=interest_rate,
            years=loan_term_years,
        )
        if monthly_payment is not None:
            metrics["monthly_payment_estimate"] = _metric(
                value=monthly_payment,
                unit="billion_vnd_per_month",
                depends_on=["loan_amount", "interest_rate_annual", "loan_term_years"],
                formula="standard amortized loan payment",
                confidence="medium",
            )

    if (
        purchase_price not in {None, 0}
        and area not in {None, 0}
        and rent_vnd is not None
    ):
        annual_rent_billion = (
            rent_vnd * max(0.0, 12 - vacancy_months) / 1_000_000_000
        )
        gross_yield = annual_rent_billion / purchase_price
        net_yield = gross_yield * (1 - operating_cost_ratio)
        metrics["gross_yield"] = _metric(
            value=round(gross_yield, 4),
            unit="ratio_0_1",
            depends_on=["expected_monthly_rent", "vacancy_months_per_year", "purchase_price"],
            formula="monthly_rent * (12 - vacancy_months) / purchase_price",
            confidence="medium",
        )
        metrics["net_yield"] = _metric(
            value=round(net_yield, 4),
            unit="ratio_0_1",
            depends_on=["gross_yield", "operating_cost_ratio"],
            formula="gross_yield * (1 - operating_cost_ratio)",
            confidence="medium",
        )
        monthly_payment = (
            _number((metrics.get("monthly_payment_estimate") or {}).get("value")) or 0.0
        )
        monthly_cashflow = (
            rent_vnd / 1_000_000_000 * (1 - operating_cost_ratio) - monthly_payment
        )
        metrics["monthly_cashflow_estimate"] = _metric(
            value=round(monthly_cashflow, 4),
            unit="billion_vnd_per_month",
            depends_on=["expected_monthly_rent", "operating_cost_ratio", "monthly_payment_estimate"],
            formula="monthly_rent_after_costs - monthly_payment",
            confidence="medium",
        )
        equity_ratio = _number((assumptions.get("equity_ratio") or {}).get("value")) or 0.0
        if equity_ratio > 0:
            metrics["cash_on_cash_return"] = _metric(
                value=round((monthly_cashflow * 12) / (purchase_price * equity_ratio), 4),
                unit="ratio_0_1",
                depends_on=["monthly_cashflow_estimate", "purchase_price", "equity_ratio"],
                formula="annual_cashflow / invested_equity",
                confidence="medium",
            )

    metrics["metric_warnings"] = _metric(
        value=len(warnings),
        unit="count",
        depends_on=[],
        formula="count(metric warning codes)",
        confidence="high",
        warnings=warnings,
    )
    return metrics
