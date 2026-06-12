from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent_service.config import get_agent_settings
from agent_service.llm.gemini import GeminiClient


ALLOWED_FILTERS = {
    "listing_type",
    "property_type",
    "city",
    "district",
    "ward",
    "min_price",
    "max_price",
    "min_area",
    "max_area",
    "bedrooms",
}


class QueryUnderstanding(BaseModel):
    original_query: str
    normalized_query: str
    rewritten_query: str
    expanded_queries: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    inferred_filters: dict[str, Any] = Field(default_factory=dict)
    missing_slots: list[str] = Field(default_factory=list)
    warnings: list[Any] = Field(default_factory=list)


def validate_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in filters.items() if key in ALLOWED_FILTERS}


def merge_query_filters(deterministic: dict[str, Any], inferred: dict[str, Any]) -> dict[str, Any]:
    return {**validate_filters(inferred), **validate_filters(deterministic)}


def _query_understanding_prompt(query: str, max_rewrites: int) -> str:
    return (
        "Phan tich query bat dong san va tra ve JSON voi rewritten_query, "
        "expanded_queries, filters, missing_slots. Khong tra loi nguoi dung. "
        f"Toi da {max_rewrites} expanded queries.\nQuery: {query}"
    )


async def build_query_understanding(
    state: dict[str, Any],
    client: GeminiClient | None = None,
) -> QueryUnderstanding:
    request = state["request"]
    from agent_service.graph.retrieval_planner import _extract_filters

    settings = get_agent_settings()
    deterministic_filters = _extract_filters(request.message)
    warnings: list[Any] = []
    inferred_filters: dict[str, Any] = {}
    rewritten_query = request.message
    expanded_queries: list[str] = []
    missing_slots: list[str] = []

    if settings.AGENT_QUERY_REWRITE_ENABLED and not state.get("force_deterministic"):
        client = client or GeminiClient()
        payload = await client.generate_json(
            _query_understanding_prompt(
                request.message,
                settings.AGENT_LLM_MAX_REWRITES,
            ),
            timeout_seconds=settings.AGENT_LLM_QUERY_TIMEOUT_SECONDS,
        )
        try:
            raw = QueryUnderstanding.model_validate(
                {
                    "original_query": request.message,
                    "normalized_query": state.get("normalized_query", ""),
                    "rewritten_query": payload.get("rewritten_query") or request.message,
                    "expanded_queries": payload.get("expanded_queries") or [],
                    "filters": {},
                    "inferred_filters": payload.get("filters") or {},
                    "missing_slots": payload.get("missing_slots") or [],
                    "warnings": [],
                }
            )
            inferred_filters = validate_filters(raw.inferred_filters)
            dropped = sorted(set(raw.inferred_filters) - set(inferred_filters))
            if dropped:
                warnings.append({"code": "query_understanding_invalid_filters", "filters": dropped})
            rewritten_query = raw.rewritten_query or request.message
            expanded_queries = raw.expanded_queries[: settings.AGENT_LLM_MAX_REWRITES]
            missing_slots = raw.missing_slots
        except Exception:
            warnings.append("query_understanding_invalid_json")

    filters = merge_query_filters(deterministic_filters, inferred_filters)
    return QueryUnderstanding(
        original_query=request.message,
        normalized_query=state.get("normalized_query", ""),
        rewritten_query=rewritten_query,
        expanded_queries=expanded_queries,
        filters=filters,
        inferred_filters=inferred_filters,
        missing_slots=missing_slots,
        warnings=warnings,
    )
