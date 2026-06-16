# Collaborative Investment Advisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a collaborative investment-advisory workflow with a shared agent blackboard, deterministic financial model, dedicated committee review node, scorecard-style synthesis, and trace metadata.

**Architecture:** Additive changes inside the existing Agent Service LangGraph workflow. Specialist agents keep producing deterministic or LLM-backed outputs, then write structured notes to a shared blackboard; new investment model and committee nodes run only for investment intent and preserve deterministic fallback behavior.

**Tech Stack:** Python 3.11, LangGraph, FastAPI, Pydantic v2, pytest, pytest-asyncio.

---

## File Structure

- Create `agent_service/graph/blackboard.py`
  - Owns blackboard entry helpers and evidence-safe appending.
- Create `agent_service/graph/investment_model.py`
  - Owns investment case building, assumption resolution, and financial metrics.
- Create `agent_service/graph/committee.py`
  - Owns deterministic committee perspectives and recommendation generation.
- Modify `agent_service/graph/state.py`
  - Adds additive state keys for blackboard and investment artifacts.
- Modify `agent_service/graph/nodes.py`
  - Adds `investment_model_node`, `committee_review_node`, blackboard entry creation after specialists, and trace output.
- Modify `agent_service/graph/workflow.py`
  - Inserts investment model and committee nodes only when `investment_advisor` participates.
- Modify `agent_service/graph/synthesis.py`
  - Adds prompt/context support for committee artifacts and deterministic scorecard formatting helper.
- Modify `agent_service/graph/react_controller.py`
  - No behavior change expected; only update tests if new warnings interact with ReAct.
- Modify `agent_service/agents/specialists.py`
  - Minimal changes only if investment output needs structured blackboard-friendly facts.
- Test files under `agent_service/tests/`
  - New focused tests for blackboard, investment model, committee review, graph flow, and safety.

---

## Task 1: State Contract And Blackboard Helpers

**Files:**
- Create: `agent_service/graph/blackboard.py`
- Modify: `agent_service/graph/state.py`
- Test: `agent_service/tests/test_agent_blackboard.py`

- [ ] **Step 1: Write the failing blackboard tests**

Create `agent_service/tests/test_agent_blackboard.py`:

```python
from __future__ import annotations

from agent_service.contracts import Evidence, AgentSource
from agent_service.graph.blackboard import (
    BlackboardEntry,
    append_blackboard_entry,
    entries_by_author,
)


def _evidence(evidence_id: str = "ev_listing_1") -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        retrieval_task_id="search_property_1",
        domain="property",
        source_type="listing",
        source_identity="listing:p1",
        record={"title": "Can ho Quan 7"},
        facts={"title": "Can ho Quan 7", "price": 4.8, "area": 75},
        source=AgentSource(
            type="listing",
            domain="property",
            id="listing:p1",
            title="Can ho Quan 7",
        ),
        retrieved_for=["investment_advisor"],
        assigned_to=["investment_advisor"],
    )


def test_append_blackboard_entry_keeps_only_known_evidence_ids():
    state = {
        "agent_blackboard": {"entries": []},
        "evidence_by_id": {"ev_listing_1": _evidence("ev_listing_1")},
    }

    updated = append_blackboard_entry(
        state,
        author="property_search",
        entry_type="property_summary",
        content={"summary": "Listing phu hop ngan sach"},
        evidence_ids=["ev_listing_1", "missing"],
        confidence="high",
        step_name="specialist_agents",
    )

    entries = updated["agent_blackboard"]["entries"]
    assert len(entries) == 1
    assert entries[0]["author"] == "property_search"
    assert entries[0]["evidence_ids"] == ["ev_listing_1"]
    assert entries[0]["confidence"] == "high"


def test_entries_by_author_filters_blackboard_entries():
    entry = BlackboardEntry(
        id="bb_property_search_1",
        author="property_search",
        type="property_summary",
        content={"summary": "ok"},
        evidence_ids=["ev1"],
        confidence="medium",
        created_at_step="specialist_agents",
    )
    blackboard = {"entries": [entry.model_dump(mode="python")]}

    assert entries_by_author(blackboard, "property_search")[0]["id"] == "bb_property_search_1"
    assert entries_by_author(blackboard, "legal_advisor") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest agent_service/tests/test_agent_blackboard.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_service.graph.blackboard'`.

- [ ] **Step 3: Add blackboard helpers**

Create `agent_service/graph/blackboard.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Confidence = Literal["low", "medium", "high"]


class BlackboardEntry(BaseModel):
    id: str
    author: str
    type: str
    content: dict[str, Any] | str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "medium"
    created_at_step: str


def _existing_evidence_ids(state: dict[str, Any]) -> set[str]:
    return set((state.get("evidence_by_id") or {}).keys())


def _next_entry_id(entries: list[dict[str, Any]], author: str) -> str:
    safe_author = author.replace(" ", "_")
    return f"bb_{safe_author}_{len(entries) + 1}"


def append_blackboard_entry(
    state: dict[str, Any],
    *,
    author: str,
    entry_type: str,
    content: dict[str, Any] | str,
    evidence_ids: list[str],
    confidence: Confidence,
    step_name: str,
) -> dict[str, Any]:
    blackboard = dict(state.get("agent_blackboard") or {})
    entries = [dict(entry) for entry in blackboard.get("entries", [])]
    valid_ids = _existing_evidence_ids(state)
    clean_evidence_ids = [
        evidence_id
        for evidence_id in evidence_ids
        if evidence_id in valid_ids and evidence_id not in []
    ]
    entry = BlackboardEntry(
        id=_next_entry_id(entries, author),
        author=author,
        type=entry_type,
        content=content,
        evidence_ids=list(dict.fromkeys(clean_evidence_ids)),
        confidence=confidence,
        created_at_step=step_name,
    )
    entries.append(entry.model_dump(mode="python"))
    blackboard["entries"] = entries
    return {"agent_blackboard": blackboard}


def entries_by_author(
    blackboard: dict[str, Any],
    author: str,
) -> list[dict[str, Any]]:
    return [
        dict(entry)
        for entry in blackboard.get("entries", [])
        if entry.get("author") == author
    ]
```

- [ ] **Step 4: Add state fields**

Modify `agent_service/graph/state.py` and add these fields to `AgentGraphState`:

```python
    agent_blackboard: dict[str, Any]
    investment_case: dict[str, Any]
    investment_assumptions: dict[str, Any]
    investment_metrics: dict[str, Any]
    committee_review: dict[str, Any]
```

- [ ] **Step 5: Run blackboard tests**

Run:

```powershell
python -m pytest agent_service/tests/test_agent_blackboard.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent_service/graph/blackboard.py agent_service/graph/state.py agent_service/tests/test_agent_blackboard.py
git commit -m "feat: add collaborative agent blackboard"
```

---

## Task 2: Investment Case Builder And Assumption Resolver

**Files:**
- Create: `agent_service/graph/investment_model.py`
- Test: `agent_service/tests/test_investment_model.py`

- [ ] **Step 1: Write failing tests for case and assumptions**

Create `agent_service/tests/test_investment_model.py`:

```python
from __future__ import annotations

from agent_service.contracts import AgentSource, Evidence
from agent_service.graph.investment_model import (
    build_investment_case,
    resolve_investment_assumptions,
)


def _evidence(
    evidence_id: str,
    *,
    domain: str,
    facts: dict,
    source_type: str = "listing",
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        retrieval_task_id=f"task_{domain}",
        domain=domain,
        source_type=source_type,
        source_identity=f"{source_type}:{evidence_id}",
        record={},
        facts=facts,
        source=AgentSource(
            type=source_type,
            domain=domain,
            id=evidence_id,
            title=str(facts.get("title") or facts.get("metric") or evidence_id),
        ),
        retrieved_for=["investment_advisor"],
        assigned_to=["investment_advisor"],
    )


def test_build_investment_case_keeps_evidence_back_links():
    evidence_by_id = {
        "ev_listing": _evidence(
            "ev_listing",
            domain="property",
            facts={
                "title": "Can ho Quan 7",
                "price": 4.8,
                "area": 75,
                "price_text": "4.8 ty",
                "area_text": "75 m2",
                "location": {"district": "Quan 7", "city": "Ho Chi Minh"},
            },
        ),
        "ev_market": _evidence(
            "ev_market",
            domain="market",
            source_type="market_metric",
            facts={
                "metric": "avg_price_per_m2",
                "value": 70,
                "unit": "million_vnd_per_m2",
                "location": {"district": "Quan 7"},
            },
        ),
    }
    case = build_investment_case(
        evidence_by_id=evidence_by_id,
        evidence_for_agent={"investment_advisor": ["ev_listing", "ev_market"]},
    )

    assert case["case_scope"] == "single_listing"
    assert case["property_summary"]["evidence_ids"] == ["ev_listing"]
    assert case["market_summary"]["evidence_ids"] == ["ev_market"]
    assert sorted(case["evidence_ids"]) == ["ev_listing", "ev_market"]


def test_resolve_assumptions_uses_user_values_then_defaults_with_ratio_units():
    case = {
        "property_summary": {
            "price": 4.8,
            "area": 75,
            "evidence_ids": ["ev_listing"],
        }
    }
    assumptions = resolve_investment_assumptions(
        case=case,
        user_inputs={"loan_ratio": 0.7, "expected_monthly_rent": 18_000_000},
        preferences={"interest_rate_annual": {"value": 0.095}},
    )

    assert assumptions["loan_ratio"]["value"] == 0.7
    assert assumptions["loan_ratio"]["unit"] == "ratio_0_1"
    assert assumptions["loan_ratio"]["source"] == "user"
    assert assumptions["interest_rate_annual"]["value"] == 0.095
    assert assumptions["interest_rate_annual"]["source"] == "preference"
    assert assumptions["operating_cost_ratio"]["value"] == 0.08
    assert assumptions["operating_cost_ratio"]["source"] == "default"
    assert assumptions["purchase_price"]["source"] == "derived"
    assert assumptions["purchase_price"]["depends_on"] == ["ev_listing"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_model.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_service.graph.investment_model'`.

- [ ] **Step 3: Create investment model module with case and assumptions**

Create `agent_service/graph/investment_model.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_model.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add agent_service/graph/investment_model.py agent_service/tests/test_investment_model.py
git commit -m "feat: build investment case and assumptions"
```

---

## Task 3: Financial Metrics With Dependency Metadata

**Files:**
- Modify: `agent_service/graph/investment_model.py`
- Test: `agent_service/tests/test_investment_metrics.py`

- [ ] **Step 1: Write failing metric tests**

Create `agent_service/tests/test_investment_metrics.py`:

```python
from __future__ import annotations

from agent_service.graph.investment_model import calculate_investment_metrics


def _assumptions() -> dict:
    return {
        "purchase_price": {
            "value": 4.8,
            "unit": "billion_vnd",
            "source": "derived",
            "depends_on": ["ev_listing"],
            "evidence_ids": ["ev_listing"],
            "note": "",
        },
        "area": {
            "value": 75,
            "unit": "m2",
            "source": "derived",
            "depends_on": ["ev_listing"],
            "evidence_ids": ["ev_listing"],
            "note": "",
        },
        "loan_ratio": {
            "value": 0.6,
            "unit": "ratio_0_1",
            "source": "default",
            "depends_on": [],
            "evidence_ids": [],
            "note": "",
        },
        "interest_rate_annual": {
            "value": 0.1,
            "unit": "ratio_0_1",
            "source": "default",
            "depends_on": [],
            "evidence_ids": [],
            "note": "",
        },
        "loan_term_years": {
            "value": 20,
            "unit": "years",
            "source": "default",
            "depends_on": [],
            "evidence_ids": [],
            "note": "",
        },
        "expected_monthly_rent": {
            "value": 18_000_000,
            "unit": "vnd_per_month",
            "source": "user",
            "depends_on": [],
            "evidence_ids": [],
            "note": "",
        },
        "vacancy_months_per_year": {
            "value": 1,
            "unit": "months",
            "source": "default",
            "depends_on": [],
            "evidence_ids": [],
            "note": "",
        },
        "operating_cost_ratio": {
            "value": 0.08,
            "unit": "ratio_0_1",
            "source": "default",
            "depends_on": [],
            "evidence_ids": [],
            "note": "",
        },
    }


def test_calculate_metrics_includes_depends_on_and_core_values():
    metrics = calculate_investment_metrics(
        case={
            "market_summary": {
                "metric": "avg_price_per_m2",
                "value": 70,
                "unit": "million_vnd_per_m2",
                "evidence_ids": ["ev_market"],
            }
        },
        assumptions=_assumptions(),
    )

    assert metrics["price_per_m2"]["value"] == 64.0
    assert metrics["price_per_m2"]["unit"] == "million_vnd_per_m2"
    assert metrics["price_per_m2"]["depends_on"] == ["purchase_price", "area"]
    assert metrics["market_price_delta"]["value"] == -0.0857
    assert "ev_market" in metrics["market_price_delta"]["depends_on"]
    assert metrics["loan_amount"]["value"] == 2.88
    assert metrics["gross_yield"]["unit"] == "ratio_0_1"
    assert metrics["monthly_cashflow_estimate"]["depends_on"]


def test_missing_price_or_area_skips_dependent_metrics():
    assumptions = _assumptions()
    assumptions.pop("area")

    metrics = calculate_investment_metrics(case={}, assumptions=assumptions)

    assert "price_per_m2" not in metrics
    assert "market_price_delta" not in metrics
    assert "missing_area" in metrics["metric_warnings"]["warnings"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_metrics.py -q
```

Expected: FAIL with `ImportError: cannot import name 'calculate_investment_metrics'`.

- [ ] **Step 3: Add metric helpers**

Append to `agent_service/graph/investment_model.py`:

```python

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
    interest_rate = _number((assumptions.get("interest_rate_annual") or {}).get("value")) or 0.0
    loan_term_years = _number((assumptions.get("loan_term_years") or {}).get("value")) or 0.0
    rent_vnd = _number((assumptions.get("expected_monthly_rent") or {}).get("value"))
    vacancy_months = _number((assumptions.get("vacancy_months_per_year") or {}).get("value")) or 0.0
    operating_cost_ratio = _number((assumptions.get("operating_cost_ratio") or {}).get("value")) or 0.0

    if purchase_price is None:
        warnings.append("missing_purchase_price")
    if area is None:
        warnings.append("missing_area")

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
            market_ids = list(market_summary.get("evidence_ids") or [])
            metrics["market_price_delta"] = _metric(
                value=round((price_per_m2 - market_avg) / market_avg, 4),
                unit="ratio_0_1",
                depends_on=["price_per_m2", *market_ids],
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

    if purchase_price not in {None, 0} and rent_vnd is not None:
        annual_rent_billion = rent_vnd * max(0.0, 12 - vacancy_months) / 1_000_000_000
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
        monthly_payment = _number((metrics.get("monthly_payment_estimate") or {}).get("value")) or 0.0
        monthly_cashflow = rent_vnd / 1_000_000_000 * (1 - operating_cost_ratio) - monthly_payment
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
    else:
        warnings.append("missing_expected_monthly_rent")

    metrics["metric_warnings"] = _metric(
        value=len(warnings),
        unit="count",
        depends_on=[],
        formula="count(metric warning codes)",
        confidence="high",
        warnings=warnings,
    )
    return metrics
```

- [ ] **Step 4: Run metric tests**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_metrics.py agent_service/tests/test_investment_model.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add agent_service/graph/investment_model.py agent_service/tests/test_investment_metrics.py
git commit -m "feat: calculate investment metrics with dependencies"
```

---

## Task 4: Investment Model Node And Trace Artifacts

**Files:**
- Modify: `agent_service/graph/nodes.py`
- Modify: `agent_service/graph/workflow.py`
- Test: `agent_service/tests/test_investment_model_node.py`

- [ ] **Step 1: Write failing node test**

Create `agent_service/tests/test_investment_model_node.py`:

```python
from __future__ import annotations

from agent_service.contracts import AgentChatRequest, AgentSource, Evidence
from agent_service.graph.nodes import investment_model_node


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="ev_listing",
        retrieval_task_id="search_property_1",
        domain="property",
        source_type="listing",
        source_identity="listing:p1",
        record={},
        facts={"title": "Can ho Quan 7", "price": 4.8, "area": 75},
        source=AgentSource(type="listing", domain="property", id="p1"),
        retrieved_for=["investment_advisor"],
        assigned_to=["investment_advisor"],
    )


def test_investment_model_node_builds_case_assumptions_metrics_and_trace():
    state = {
        "request": AgentChatRequest(
            request_id="req-invest-node",
            session_id="s1",
            message="Co nen dau tu can ho nay khong?",
            user_preferences={"interest_rate_annual": {"value": 0.095}},
        ),
        "agents_to_run": ["investment_advisor"],
        "evidence_by_id": {"ev_listing": _evidence()},
        "evidence_for_agent": {"investment_advisor": ["ev_listing"]},
        "query_understanding": {
            "filters": {
                "expected_monthly_rent": 18_000_000,
                "loan_ratio": 0.6,
            }
        },
        "trace_steps": [],
        "warnings": [],
    }

    result = investment_model_node(state)

    assert result["investment_case"]["property_summary"]["evidence_ids"] == ["ev_listing"]
    assert result["investment_assumptions"]["loan_ratio"]["value"] == 0.6
    assert "price_per_m2" in result["investment_metrics"]
    assert result["trace_steps"][-1]["step_name"] == "investment_model"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_model_node.py -q
```

Expected: FAIL with `ImportError: cannot import name 'investment_model_node'`.

- [ ] **Step 3: Add node implementation**

Modify `agent_service/graph/nodes.py` imports:

```python
from agent_service.graph.investment_model import (
    build_investment_case,
    calculate_investment_metrics,
    resolve_investment_assumptions,
)
```

Add this node after `specialist_agents_node`:

```python
def investment_model_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    if "investment_advisor" not in state.get("agents_to_run", []):
        return {
            "trace_steps": _append_trace(
                state,
                "investment_model",
                start_time,
                {"skipped": True, "reason": "investment_advisor_not_selected"},
            )
        }

    understanding = state.get("query_understanding") or {}
    user_inputs = dict(understanding.get("filters") or {})
    case = build_investment_case(
        evidence_by_id=state.get("evidence_by_id", {}),
        evidence_for_agent=state.get("evidence_for_agent", {}),
    )
    assumptions = resolve_investment_assumptions(
        case=case,
        user_inputs=user_inputs,
        preferences=state["request"].user_preferences,
    )
    metrics = calculate_investment_metrics(
        case=case,
        assumptions=assumptions,
    )
    return {
        "investment_case": case,
        "investment_assumptions": assumptions,
        "investment_metrics": metrics,
        "trace_steps": _append_trace(
            state,
            "investment_model",
            start_time,
            {
                "case_scope": case.get("case_scope"),
                "metric_keys": list(metrics),
                "missing_evidence": case.get("missing_evidence", []),
            },
        ),
    }
```

- [ ] **Step 4: Insert node into workflow**

Modify imports in `agent_service/graph/workflow.py`:

```python
    investment_model_node,
```

Add route helpers:

```python
def _route_after_specialists(state: AgentGraphState) -> str:
    return (
        "investment_model"
        if "investment_advisor" in state.get("agents_to_run", [])
        else "synthesizer"
    )


def _route_after_investment_model(state: AgentGraphState) -> str:
    return "committee_review"
```

Add node:

```python
    workflow.add_node("investment_model", investment_model_node)
```

Replace the direct edge from specialists to synthesizer:

```python
    workflow.add_conditional_edges(
        "specialist_agents",
        _route_after_specialists,
        {
            "investment_model": "investment_model",
            "synthesizer": "synthesizer",
        },
    )
    workflow.add_conditional_edges(
        "investment_model",
        _route_after_investment_model,
        {"committee_review": "committee_review"},
    )
```

The `committee_review` node is added in Task 5. If doing Task 4 alone, point
`investment_model` to `synthesizer` until Task 5 is implemented:

```python
    workflow.add_edge("investment_model", "synthesizer")
```

- [ ] **Step 5: Run node test**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_model_node.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent_service/graph/nodes.py agent_service/graph/workflow.py agent_service/tests/test_investment_model_node.py
git commit -m "feat: add investment model graph node"
```

---

## Task 5: Deterministic Committee Review

**Files:**
- Create: `agent_service/graph/committee.py`
- Modify: `agent_service/graph/nodes.py`
- Modify: `agent_service/graph/workflow.py`
- Test: `agent_service/tests/test_committee_review.py`

- [ ] **Step 1: Write failing committee tests**

Create `agent_service/tests/test_committee_review.py`:

```python
from __future__ import annotations

from agent_service.graph.committee import build_committee_review


def test_committee_review_returns_structured_perspectives_and_need_more_info():
    review = build_committee_review(
        investment_case={
            "missing_evidence": ["market", "legal"],
            "property_summary": {"evidence_ids": ["ev_listing"]},
            "market_summary": {"evidence_ids": []},
            "legal_summary": {"evidence_ids": []},
        },
        investment_assumptions={
            "expected_monthly_rent": {
                "value": None,
                "source": "default",
                "depends_on": [],
                "evidence_ids": [],
                "unit": "vnd_per_month",
                "note": "",
            }
        },
        investment_metrics={
            "price_per_m2": {
                "value": 64.0,
                "unit": "million_vnd_per_m2",
                "depends_on": ["purchase_price", "area"],
                "formula": "",
                "confidence": "high",
                "warnings": [],
            },
            "metric_warnings": {
                "value": 1,
                "unit": "count",
                "depends_on": [],
                "formula": "",
                "confidence": "high",
                "warnings": ["missing_expected_monthly_rent"],
            },
        },
        agent_blackboard={"entries": []},
        warnings=[],
    )

    roles = {item["role"] for item in review["perspectives"]}
    assert {"bull", "bear", "legal_risk", "market_risk", "finance", "missing_inputs"}.issubset(roles)
    assert review["recommendation"]["decision"] == "need_more_info"
    assert review["recommendation"]["confidence"] == "low"
    assert "expected_monthly_rent" in review["recommendation"]["required_confirmations"]


def test_committee_review_consider_is_not_high_confidence_when_defaults_drive_metrics():
    review = build_committee_review(
        investment_case={
            "missing_evidence": [],
            "property_summary": {"evidence_ids": ["ev_listing"]},
            "market_summary": {"evidence_ids": ["ev_market"]},
            "legal_summary": {"evidence_ids": ["ev_legal"]},
        },
        investment_assumptions={
            "loan_ratio": {
                "value": 0.6,
                "source": "default",
                "depends_on": [],
                "evidence_ids": [],
                "unit": "ratio_0_1",
                "note": "",
            },
            "expected_monthly_rent": {
                "value": 18_000_000,
                "source": "user",
                "depends_on": [],
                "evidence_ids": [],
                "unit": "vnd_per_month",
                "note": "",
            },
        },
        investment_metrics={
            "net_yield": {
                "value": 0.0414,
                "unit": "ratio_0_1",
                "depends_on": ["gross_yield", "operating_cost_ratio"],
                "formula": "",
                "confidence": "medium",
                "warnings": [],
            },
            "monthly_cashflow_estimate": {
                "value": -0.0101,
                "unit": "billion_vnd_per_month",
                "depends_on": [],
                "formula": "",
                "confidence": "medium",
                "warnings": [],
            },
            "metric_warnings": {
                "value": 0,
                "unit": "count",
                "depends_on": [],
                "formula": "",
                "confidence": "high",
                "warnings": [],
            },
        },
        agent_blackboard={"entries": []},
        warnings=[],
    )

    assert review["recommendation"]["decision"] in {"consider", "wait"}
    assert review["recommendation"]["confidence"] in {"low", "medium"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest agent_service/tests/test_committee_review.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_service.graph.committee'`.

- [ ] **Step 3: Create committee module**

Create `agent_service/graph/committee.py`:

```python
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
    property_ids = list((investment_case.get("property_summary") or {}).get("evidence_ids") or [])
    market_ids = list((investment_case.get("market_summary") or {}).get("evidence_ids") or [])
    legal_ids = list((investment_case.get("legal_summary") or {}).get("evidence_ids") or [])
    metric_warnings = list((investment_metrics.get("metric_warnings") or {}).get("warnings") or [])
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
            suggested_actions=["Xac nhan tien thue ky vong", "So sanh them listing cung khu vuc"],
        ),
        _perspective(
            role="bear",
            stance="negative",
            summary=bear_summary,
            evidence_ids=property_ids,
            depends_on=["monthly_cashflow_estimate", *default_or_estimated],
            confidence="medium",
            risk_level="medium" if monthly_cashflow is not None else "high",
            suggested_actions=["Kiem tra lai gia mua", "Tinh kich ban lai suat cao hon"],
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
            suggested_actions=["Kiem tra so hong", "Kiem tra quy hoach", "Hoi chuyen gia phap ly"],
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
            suggested_actions=["Lay them benchmark gia/m2", "So sanh lich su giao dich khu vuc"],
        ),
        _perspective(
            role="finance",
            stance="negative" if monthly_cashflow is not None and monthly_cashflow < 0 else "neutral",
            summary="Mo hinh tai chinh dang dua tren cac gia dinh can xac nhan.",
            evidence_ids=property_ids,
            depends_on=list(investment_metrics),
            confidence="medium" if "expected_monthly_rent" not in required_confirmations else "low",
            risk_level="medium",
            suggested_actions=["Xac nhan lai suat vay", "Xac nhan ty le vay", "Xac nhan tien thue"],
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
            "rationale": "Recommendation derived from financial metrics, missing inputs, and evidence availability.",
            "required_confirmations": list(dict.fromkeys(required_confirmations)),
        },
    }
```

- [ ] **Step 4: Add committee node**

Modify `agent_service/graph/nodes.py` imports:

```python
from agent_service.graph.committee import build_committee_review
```

Add node after `investment_model_node`:

```python
def committee_review_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    if "investment_advisor" not in state.get("agents_to_run", []):
        return {
            "trace_steps": _append_trace(
                state,
                "committee_review",
                start_time,
                {"skipped": True, "reason": "investment_advisor_not_selected"},
            )
        }
    review = build_committee_review(
        investment_case=state.get("investment_case", {}),
        investment_assumptions=state.get("investment_assumptions", {}),
        investment_metrics=state.get("investment_metrics", {}),
        agent_blackboard=state.get("agent_blackboard", {}),
        warnings=state.get("warnings", []),
    )
    return {
        "committee_review": review,
        "trace_steps": _append_trace(
            state,
            "committee_review",
            start_time,
            {
                "perspective_count": len(review.get("perspectives", [])),
                "decision": (review.get("recommendation") or {}).get("decision"),
            },
        ),
    }
```

- [ ] **Step 5: Wire committee node into workflow**

Modify `agent_service/graph/workflow.py` imports:

```python
    committee_review_node,
```

Add node:

```python
    workflow.add_node("committee_review", committee_review_node)
```

Ensure investment path runs:

```python
    workflow.add_edge("investment_model", "committee_review")
    workflow.add_edge("committee_review", "synthesizer")
```

The normal non-investment path must remain:

```python
    workflow.add_conditional_edges(
        "specialist_agents",
        _route_after_specialists,
        {
            "investment_model": "investment_model",
            "synthesizer": "synthesizer",
        },
    )
```

- [ ] **Step 6: Run committee tests**

Run:

```powershell
python -m pytest agent_service/tests/test_committee_review.py agent_service/tests/test_investment_model_node.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add agent_service/graph/committee.py agent_service/graph/nodes.py agent_service/graph/workflow.py agent_service/tests/test_committee_review.py
git commit -m "feat: add investment committee review node"
```

---

## Task 6: Blackboard Entries From Specialist Results

**Files:**
- Modify: `agent_service/graph/nodes.py`
- Test: `agent_service/tests/test_blackboard_specialists.py`

- [ ] **Step 1: Write failing specialist blackboard test**

Create `agent_service/tests/test_blackboard_specialists.py`:

```python
from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest, AgentSource, Evidence
from agent_service.graph import nodes


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="ev_listing",
        retrieval_task_id="search_property_1",
        domain="property",
        source_type="listing",
        source_identity="listing:p1",
        record={},
        facts={"title": "Can ho Quan 7", "price": 4.8, "area": 75},
        source=AgentSource(type="listing", domain="property", id="p1"),
        retrieved_for=["property_search", "investment_advisor"],
        assigned_to=["property_search", "investment_advisor"],
    )


@pytest.mark.asyncio
async def test_specialist_agents_node_writes_blackboard_entries(monkeypatch):
    async def fake_property_agent(**kwargs):
        return {
            "agent_name": "property_search",
            "status": "completed",
            "content": "Listing phu hop de sang loc dau tu.",
            "evidence_ids_used": ["ev_listing"],
            "confidence": "high",
            "warnings": [],
        }

    monkeypatch.setattr(nodes, "run_property_agent", fake_property_agent)
    state = {
        "request": AgentChatRequest(
            request_id="req-bb-specialist",
            session_id="s1",
            message="Co nen dau tu can ho nay?",
        ),
        "agents_to_run": ["property_search"],
        "evidence_by_id": {"ev_listing": _evidence()},
        "evidence_for_agent": {"property_search": ["ev_listing"]},
        "readiness": {},
        "warnings": [],
        "trace_steps": [],
        "force_deterministic": True,
    }

    result = await nodes.specialist_agents_node(state)

    entries = result["agent_blackboard"]["entries"]
    assert entries[0]["author"] == "property_search"
    assert entries[0]["evidence_ids"] == ["ev_listing"]
    assert entries[0]["content"]["status"] == "completed"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest agent_service/tests/test_blackboard_specialists.py -q
```

Expected: FAIL because `specialist_agents_node` does not return `agent_blackboard`.

- [ ] **Step 3: Add blackboard conversion helper**

Modify `agent_service/graph/nodes.py` imports:

```python
from agent_service.graph.blackboard import append_blackboard_entry
```

Add helper above `specialist_agents_node`:

```python
def _blackboard_from_agent_results(
    state: AgentGraphState,
    agent_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    update: dict[str, Any] = {"agent_blackboard": state.get("agent_blackboard", {"entries": []})}
    working_state = {**state, **update}
    for agent, result in agent_results.items():
        evidence_ids = [str(value) for value in result.get("evidence_ids_used", [])]
        confidence = str(result.get("confidence") or "medium")
        if confidence not in {"low", "medium", "high"}:
            confidence = "medium"
        update = append_blackboard_entry(
            {**working_state, **update},
            author=agent,
            entry_type="specialist_result",
            content={
                "status": result.get("status"),
                "content": result.get("content", ""),
                "missing_evidence": result.get("missing_evidence", []),
                "warnings": [
                    warning.code if hasattr(warning, "code") else warning
                    for warning in result.get("warnings", [])
                ],
            },
            evidence_ids=evidence_ids,
            confidence=confidence,
            step_name="specialist_agents",
        )
        working_state = {**working_state, **update}
    return update
```

- [ ] **Step 4: Return blackboard from specialist node**

At the end of `specialist_agents_node`, before return:

```python
    blackboard_update = _blackboard_from_agent_results(state, agent_results)
```

Return:

```python
    return {
        "agent_results": agent_results,
        **blackboard_update,
        "trace_steps": _append_trace(
            state,
            "specialist_agents",
            start_time,
            {
                "agents_completed": list(agent_results),
                "blackboard_entries": len(
                    blackboard_update.get("agent_blackboard", {}).get("entries", [])
                ),
            },
        ),
    }
```

- [ ] **Step 5: Run specialist blackboard tests**

Run:

```powershell
python -m pytest agent_service/tests/test_blackboard_specialists.py agent_service/tests/test_specialists_parallel.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent_service/graph/nodes.py agent_service/tests/test_blackboard_specialists.py
git commit -m "feat: write specialist outputs to blackboard"
```

---

## Task 7: Scorecard Synthesis For Committee Reviews

**Files:**
- Modify: `agent_service/graph/synthesis.py`
- Modify: `agent_service/graph/nodes.py`
- Test: `agent_service/tests/test_investment_scorecard_synthesis.py`

- [ ] **Step 1: Write failing scorecard tests**

Create `agent_service/tests/test_investment_scorecard_synthesis.py`:

```python
from __future__ import annotations

from agent_service.graph.synthesis import format_investment_scorecard


def test_format_investment_scorecard_includes_scorecard_assumptions_and_checklist():
    response = format_investment_scorecard(
        committee_review={
            "recommendation": {
                "decision": "need_more_info",
                "confidence": "low",
                "rationale": "Need rent and legal confirmation.",
                "required_confirmations": ["expected_monthly_rent", "legal_documents"],
            },
            "perspectives": [
                {
                    "role": "bull",
                    "summary": "Gia/m2 co the hop ly neu benchmark dung.",
                    "suggested_actions": ["So sanh them listing"],
                },
                {
                    "role": "bear",
                    "summary": "Dong tien chua chac chan.",
                    "suggested_actions": ["Xac nhan tien thue"],
                },
            ],
        },
        investment_assumptions={
            "loan_ratio": {
                "value": 0.6,
                "unit": "ratio_0_1",
                "source": "default",
                "note": "loan_ratio resolved from default.",
            },
            "expected_monthly_rent": {
                "value": None,
                "unit": "vnd_per_month",
                "source": "default",
                "note": "Expected monthly rent is missing.",
            },
        },
        investment_metrics={
            "price_per_m2": {
                "value": 64.0,
                "unit": "million_vnd_per_m2",
                "confidence": "high",
                "warnings": [],
            },
            "metric_warnings": {
                "warnings": ["missing_expected_monthly_rent"],
            },
        },
    )

    assert "Scorecard dau tu" in response
    assert "need_more_info" in response
    assert "64.0 million_vnd_per_m2" in response
    assert "loan_ratio=0.6" in response
    assert "Checklist hanh dong" in response
    assert "khong phai loi khuyen tai chinh" in response
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_scorecard_synthesis.py -q
```

Expected: FAIL with `ImportError: cannot import name 'format_investment_scorecard'`.

- [ ] **Step 3: Add scorecard formatter**

Append to `agent_service/graph/synthesis.py`:

```python

def _compact_value(value: object) -> str:
    return "missing" if value is None else str(value)


def format_investment_scorecard(
    *,
    committee_review: dict[str, Any],
    investment_assumptions: dict[str, dict[str, Any]],
    investment_metrics: dict[str, dict[str, Any]],
) -> str:
    recommendation = committee_review.get("recommendation") or {}
    perspectives = list(committee_review.get("perspectives") or [])
    metric_lines = []
    for key in (
        "price_per_m2",
        "market_price_delta",
        "gross_yield",
        "net_yield",
        "monthly_cashflow_estimate",
        "cash_on_cash_return",
    ):
        metric = investment_metrics.get(key)
        if not metric:
            continue
        metric_lines.append(
            f"- {key}: {_compact_value(metric.get('value'))} {metric.get('unit')} "
            f"(confidence: {metric.get('confidence')})"
        )
    assumption_lines = []
    for key, assumption in investment_assumptions.items():
        if assumption.get("source") in {"default", "estimated"} or assumption.get("value") is None:
            assumption_lines.append(
                f"- {key}={_compact_value(assumption.get('value'))} "
                f"{assumption.get('unit')} (source: {assumption.get('source')})"
            )
    perspective_lines = [
        f"- {item.get('role')}: {item.get('summary')}"
        for item in perspectives
        if item.get("summary")
    ]
    actions: list[str] = []
    for item in perspectives:
        for action in item.get("suggested_actions") or []:
            if action not in actions:
                actions.append(str(action))
    for confirmation in recommendation.get("required_confirmations") or []:
        action = f"Xac nhan {confirmation}"
        if action not in actions:
            actions.append(action)
    return "\n".join(
        [
            "Scorecard dau tu",
            f"- Decision: {recommendation.get('decision')}",
            f"- Confidence: {recommendation.get('confidence')}",
            f"- Rationale: {recommendation.get('rationale')}",
            "Chi so chinh:",
            *(metric_lines or ["- Chua du chi so tai chinh de ket luan."]),
            "Gia dinh can xac nhan:",
            *(assumption_lines or ["- Khong co gia dinh mac dinh can neu them."]),
            "Goc nhin committee:",
            *(perspective_lines or ["- Chua co goc nhin committee."]),
            "Checklist hanh dong:",
            *(f"- {action}" for action in (actions or ["Xac nhan them du lieu dau vao"])),
            "Luu y: Phan tich nay khong phai loi khuyen tai chinh.",
        ]
    )
```

- [ ] **Step 4: Use scorecard in synthesizer node**

Modify `agent_service/graph/nodes.py` imports:

```python
from agent_service.graph.synthesis import (
    format_investment_scorecard,
    synthesize_final_answer,
)
```

Inside `synthesizer_node`, after deterministic `final_response` is built and before `synthesize_final_answer(...)`:

```python
    if state.get("committee_review"):
        final_response = format_investment_scorecard(
            committee_review=state.get("committee_review", {}),
            investment_assumptions=state.get("investment_assumptions", {}),
            investment_metrics=state.get("investment_metrics", {}),
        )
        suggested_actions = [
            "Xac nhan tien thue ky vong",
            "Xac nhan ty le vay va lai suat",
            "Kiem tra phap ly",
        ]
```

- [ ] **Step 5: Run synthesis tests**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_scorecard_synthesis.py agent_service/tests/test_synthesis.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent_service/graph/synthesis.py agent_service/graph/nodes.py agent_service/tests/test_investment_scorecard_synthesis.py
git commit -m "feat: format investment committee scorecards"
```

---

## Task 8: Full Trace Serialization

**Files:**
- Modify: `agent_service/graph/workflow.py`
- Test: `agent_service/tests/test_investment_trace.py`

- [ ] **Step 1: Write failing trace test**

Create `agent_service/tests/test_investment_trace.py`:

```python
from __future__ import annotations

from agent_service.contracts import AgentChatRequest
from agent_service.graph.workflow import _response_from_result


def test_response_full_trace_includes_investment_artifacts():
    request = AgentChatRequest(
        request_id="req-trace-invest",
        session_id="s1",
        message="Co nen dau tu can ho nay?",
    )
    response = _response_from_result(
        request,
        {
            "intent": "investment_advice",
            "agents_to_run": ["investment_advisor"],
            "final_response": "Scorecard dau tu",
            "sources": [],
            "suggested_actions": [],
            "trace_steps": [],
            "warnings": [],
            "agent_blackboard": {"entries": [{"id": "bb1"}]},
            "investment_case": {"case_scope": "single_listing"},
            "investment_assumptions": {"loan_ratio": {"value": 0.6}},
            "investment_metrics": {"price_per_m2": {"value": 64.0}},
            "committee_review": {"recommendation": {"decision": "need_more_info"}},
        },
    )

    trace = response.full_trace
    assert trace["agent_blackboard"]["entries"][0]["id"] == "bb1"
    assert trace["investment_case"]["case_scope"] == "single_listing"
    assert trace["investment_metrics"]["price_per_m2"]["value"] == 64.0
    assert trace["committee_review"]["recommendation"]["decision"] == "need_more_info"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_trace.py -q
```

Expected: FAIL because `_response_from_result` does not include investment artifacts in `full_trace`.

- [ ] **Step 3: Add artifacts to full trace**

Modify `_response_from_result` in `agent_service/graph/workflow.py`. In the `full_trace={...}` dictionary, add:

```python
            "agent_blackboard": result.get("agent_blackboard", {"entries": []}),
            "investment_case": result.get("investment_case", {}),
            "investment_assumptions": result.get("investment_assumptions", {}),
            "investment_metrics": result.get("investment_metrics", {}),
            "committee_review": result.get("committee_review", {}),
```

- [ ] **Step 4: Run trace test**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_trace.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add agent_service/graph/workflow.py agent_service/tests/test_investment_trace.py
git commit -m "feat: expose investment artifacts in trace"
```

---

## Task 9: Safety Validation For Committee Outputs

**Files:**
- Modify: `agent_service/graph/nodes.py`
- Test: `agent_service/tests/test_investment_safety.py`

- [ ] **Step 1: Write failing safety tests**

Create `agent_service/tests/test_investment_safety.py`:

```python
from __future__ import annotations

from agent_service.graph.nodes import safety_validator_node


def test_safety_warns_when_investment_answer_lacks_disclaimer():
    result = safety_validator_node(
        {
            "final_response": "Nen dau tu ngay.",
            "sources": [],
            "suggested_actions": [],
            "agents_to_run": ["investment_advisor"],
            "warnings": [],
            "agent_results": {},
            "evidence_by_id": {},
            "evidence_for_agent": {},
            "trace_steps": [],
        }
    )

    assert "financial_disclaimer_missing" in result["warnings"]


def test_safety_downgrades_high_confidence_committee_with_missing_inputs():
    result = safety_validator_node(
        {
            "final_response": "Scorecard dau tu\nLuu y: khong phai loi khuyen tai chinh.",
            "sources": [],
            "suggested_actions": [],
            "agents_to_run": ["investment_advisor"],
            "warnings": [],
            "agent_results": {},
            "evidence_by_id": {},
            "evidence_for_agent": {},
            "committee_review": {
                "recommendation": {
                    "decision": "consider",
                    "confidence": "high",
                    "required_confirmations": ["expected_monthly_rent"],
                }
            },
            "trace_steps": [],
        }
    )

    assert "committee_high_confidence_with_missing_inputs" in result["warnings"]
    assert result["committee_review"]["recommendation"]["confidence"] == "medium"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_safety.py -q
```

Expected: first test may PASS with existing disclaimer logic; second test FAIL because committee confidence is not downgraded.

- [ ] **Step 3: Add committee confidence safety check**

Inside `safety_validator_node` in `agent_service/graph/nodes.py`, after disclaimer checks:

```python
    committee_review = dict(state.get("committee_review") or {})
    recommendation = dict(committee_review.get("recommendation") or {})
    if (
        "investment_advisor" in agents_to_run
        and recommendation.get("confidence") == "high"
        and recommendation.get("required_confirmations")
    ):
        recommendation["confidence"] = "medium"
        committee_review["recommendation"] = recommendation
        added_warnings.append("committee_high_confidence_with_missing_inputs")
```

In the return dictionary from `safety_validator_node`, add:

```python
        "committee_review": committee_review if committee_review else state.get("committee_review", {}),
```

- [ ] **Step 4: Run safety tests**

Run:

```powershell
python -m pytest agent_service/tests/test_investment_safety.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add agent_service/graph/nodes.py agent_service/tests/test_investment_safety.py
git commit -m "feat: validate investment committee confidence"
```

---

## Task 10: End-To-End Investment Graph Smoke

**Files:**
- Test: `agent_service/tests/test_collaborative_investment_graph.py`

- [ ] **Step 1: Write graph smoke test**

Create `agent_service/tests/test_collaborative_investment_graph.py`:

```python
from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph import nodes
from agent_service.graph import retrieval_planner
from agent_service.graph.workflow import run_agent_graph


@pytest.mark.asyncio
async def test_collaborative_investment_graph_returns_scorecard_and_trace(monkeypatch):
    async def fake_readiness_snapshot():
        return {
            "listings": {"status": "ready", "parent_count": 1, "chunk_count": 1},
            "projects": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "news": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "legal": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
        }

    async def fake_run_hybrid_tool(**kwargs):
        if kwargs["parent_type"] == "listing":
            return [
                {
                    "id": 1,
                    "product_id": "p1",
                    "title": "Can ho Quan 7",
                    "price": 4.8,
                    "area": 75,
                    "price_text": "4.8 ty",
                    "area_text": "75 m2",
                    "url": "https://example.test/p1",
                    "matched_chunk": {
                        "id": "chunk1",
                        "text": "Can ho Quan 7 gia 4.8 ty dien tich 75 m2",
                        "rerank_score": 0.9,
                    },
                }
            ]
        return []

    monkeypatch.setattr(nodes, "build_readiness_snapshot", fake_readiness_snapshot)
    monkeypatch.setattr(retrieval_planner, "_run_hybrid_tool", fake_run_hybrid_tool)

    response = await run_agent_graph(
        AgentChatRequest(
            request_id="req-collab-invest",
            session_id="s1",
            message="Co nen dau tu can ho Quan 7 nay khong?",
        )
    )

    assert "Scorecard dau tu" in response.final_response
    assert "khong phai loi khuyen tai chinh" in response.final_response
    assert response.full_trace["investment_case"]
    assert response.full_trace["investment_metrics"]
    assert response.full_trace["committee_review"]["perspectives"]
```

- [ ] **Step 2: Run graph smoke test**

Run:

```powershell
python -m pytest agent_service/tests/test_collaborative_investment_graph.py -q
```

Expected: PASS after Tasks 1-9.

- [ ] **Step 3: Run focused agent service regression**

Run:

```powershell
python -m pytest agent_service/tests -q
```

Expected: PASS.

- [ ] **Step 4: Compile Agent Service**

Run:

```powershell
python -m compileall agent_service
```

Expected: PASS with no syntax errors.

- [ ] **Step 5: Commit**

```powershell
git add agent_service/tests/test_collaborative_investment_graph.py
git commit -m "test: cover collaborative investment graph flow"
```

---

## Verification Matrix

Run focused checks:

```powershell
python -m pytest agent_service/tests/test_agent_blackboard.py agent_service/tests/test_investment_model.py agent_service/tests/test_investment_metrics.py agent_service/tests/test_committee_review.py -q
python -m pytest agent_service/tests/test_investment_model_node.py agent_service/tests/test_blackboard_specialists.py agent_service/tests/test_investment_scorecard_synthesis.py agent_service/tests/test_investment_trace.py agent_service/tests/test_investment_safety.py -q
python -m pytest agent_service/tests/test_collaborative_investment_graph.py -q
```

Run full Agent Service suite:

```powershell
python -m pytest agent_service/tests -q
python -m compileall agent_service
```

Run backend compatibility checks:

```powershell
python -m pytest backend/tests/test_chat_agent_service_integration.py backend/tests/test_agent_service_client.py -q
python -m compileall backend\app
```

## Self-Review

- Spec coverage: plan covers blackboard, evidence back-links, assumptions with
  `derived`, ratio units, metric `depends_on`, structured `Perspective`
  committee review, dedicated committee node, trace metadata, scorecard output,
  checklist output, and safety confidence downgrade.
- Scope control: plan does not add `DealReview` persistence, frontend UI,
  crawler changes, ingestion changes, or live LLM dependency.
- Type consistency: state fields match the approved spec:
  `agent_blackboard`, `investment_case`, `investment_assumptions`,
  `investment_metrics`, and `committee_review`.
- Testability: each task introduces focused tests before implementation and
  keeps commits small enough to review independently.

