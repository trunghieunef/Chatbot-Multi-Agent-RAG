from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MemoryFilterResult(BaseModel):
    filters: dict[str, Any] = Field(default_factory=dict)
    applied_keys: list[str] = Field(default_factory=list)
    skipped_keys: list[str] = Field(default_factory=list)
    warnings: list[Any] = Field(default_factory=list)


PREFERENCE_TO_FILTER = {
    "preferred_city": "city",
    "preferred_district": "district",
    "preferred_property_type": "property_type",
    "listing_type": "listing_type",
    "bedrooms": "bedrooms",
    "max_budget": "max_price",
    "min_budget": "min_price",
}


def _preference_value(user_preferences: dict[str, Any], key: str) -> Any:
    value = user_preferences.get(key)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _budget_value(user_preferences: dict[str, Any], bound: str) -> Any:
    budget = user_preferences.get("budget")
    if isinstance(budget, dict):
        if "value" in budget and isinstance(budget["value"], dict):
            return budget["value"].get(bound)
        return budget.get(bound)
    return None


def derive_memory_filters(
    user_preferences: dict[str, Any],
    current_filters: dict[str, Any],
    query: str,
) -> MemoryFilterResult:
    del query
    filters = dict(current_filters)
    applied = []
    skipped = []
    warnings = []

    candidates = {
        pref_key: _preference_value(user_preferences, pref_key)
        for pref_key in PREFERENCE_TO_FILTER
    }
    candidates["max_budget"] = candidates.get("max_budget") or _budget_value(
        user_preferences,
        "max",
    )
    candidates["min_budget"] = candidates.get("min_budget") or _budget_value(
        user_preferences,
        "min",
    )

    for pref_key, filter_key in PREFERENCE_TO_FILTER.items():
        value = candidates.get(pref_key)
        if value is None or value == "":
            continue
        if filter_key in current_filters:
            skipped.append(pref_key)
            continue
        filters[filter_key] = value
        applied.append(pref_key)

    return MemoryFilterResult(
        filters=filters,
        applied_keys=applied,
        skipped_keys=skipped,
        warnings=warnings,
    )
