from __future__ import annotations

from typing import Any

from agent_service.contracts import MemoryProposal


FILTER_TO_MEMORY_KEY = {
    "city": "preferred_city",
    "district": "preferred_district",
    "property_type": "preferred_property_type",
    "listing_type": "listing_type",
    "bedrooms": "bedrooms",
    "max_price": "max_budget",
    "min_price": "min_budget",
}


def _confidence_for_key(key: str) -> float:
    if key in {"preferred_district", "preferred_city", "listing_type"}:
        return 0.82
    if key in {"max_budget", "min_budget", "bedrooms"}:
        return 0.78
    return 0.72


def extract_memory_proposals(
    *,
    query: str,
    filters: dict[str, Any],
) -> list[MemoryProposal]:
    proposals: list[MemoryProposal] = []
    clean_query = query.strip()
    for filter_key, memory_key in FILTER_TO_MEMORY_KEY.items():
        value = filters.get(filter_key)
        if value is None or value == "":
            continue
        proposals.append(
            MemoryProposal(
                action="upsert",
                key=memory_key,
                value=value,
                confidence=_confidence_for_key(memory_key),
                evidence=(
                    f"Current query implied {memory_key}: {value}. "
                    f"Query: {clean_query[:160]}"
                ),
                requires_user_confirmation=True,
            )
        )
    return proposals
