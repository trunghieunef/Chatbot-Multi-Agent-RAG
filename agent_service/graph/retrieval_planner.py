from __future__ import annotations

import re
import unicodedata
from typing import Any

from agent_service.contracts import RetrievalTask
from agent_service.graph.state import AgentGraphState


DOMAIN_SOURCE = {
    "property": "listings",
    "project": "projects",
    "news": "news",
    "legal": "legal",
    "market": "listings",
}


def _strip_accents(value: str | None) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    ).lower()


def _extract_filters(query: str) -> dict[str, Any]:
    normalized = _strip_accents(query)
    filters: dict[str, Any] = {}

    if any(term in normalized for term in ("thue", "cho thue")):
        filters["listing_type"] = "rent"
    elif any(term in normalized for term in ("tim", "mua", "ban", "dau tu")):
        filters["listing_type"] = "sale"

    if "can ho" in normalized or "chung cu" in normalized:
        filters["property_type"] = "Can ho"

    district_match = re.search(r"\b(?:quan|q)\s*(\d{1,2})\b", normalized)
    if district_match:
        filters["district"] = f"Quan {district_match.group(1)}"

    max_price_match = re.search(
        r"(?:duoi|toi da|khong qua)\s*(\d+(?:[\.,]\d+)?)\s*(?:ty|ti)",
        normalized,
    )
    if max_price_match:
        filters["max_price"] = float(max_price_match.group(1).replace(",", "."))

    return filters


def readiness_capabilities(readiness: dict[str, Any]) -> dict[str, dict[str, bool]]:
    capabilities: dict[str, dict[str, bool]] = {}
    for domain, source_name in DOMAIN_SOURCE.items():
        source = readiness.get(source_name, {})
        if isinstance(source, dict):
            parent_count = int(source.get("parent_count") or 0)
            chunk_count = int(source.get("chunk_count") or 0)
        else:
            parent_count = 0
            chunk_count = 0

        capabilities[domain] = {
            "parent_ready": parent_count > 0,
            "structured_search_ready": parent_count > 0,
            "semantic_index_ready": parent_count > 0 and chunk_count > 0,
            "market_aggregate_ready": parent_count > 0 and domain in {"property", "market"},
        }
    return capabilities


def _needs_project(query: str) -> bool:
    normalized = _strip_accents(query)
    return any(term in normalized for term in ("du an", "chu dau tu", "ha tang"))


def _needs_news(query: str) -> bool:
    normalized = _strip_accents(query)
    return any(
        term in normalized
        for term in ("tin tuc", "bien dong", "cap nhat", "thi truong gan day")
    )


def _location_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in filters.items()
        if key in {"district", "city"}
    }


def build_retrieval_plan(state: AgentGraphState) -> list[RetrievalTask]:
    request = state["request"]
    agents = list(state.get("agents_to_run", []))
    caps = readiness_capabilities(state.get("readiness", {}))
    query = request.message
    listing_filters = _extract_filters(query)
    plan: list[RetrievalTask] = []

    if "property_search" in agents and caps["property"]["semantic_index_ready"]:
        plan.append(
            RetrievalTask(
                task_id="search_property_1",
                domain="property",
                tool="search_listings",
                query=query,
                filters=listing_filters,
                retrieved_for=["property_search"],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    if "legal_advisor" in agents and caps["legal"]["semantic_index_ready"]:
        plan.append(
            RetrievalTask(
                task_id="search_legal_1",
                domain="legal",
                tool="search_articles",
                query=query,
                filters={"category": "legal"},
                retrieved_for=["legal_advisor"],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    if "project_agent" in agents and caps["project"]["semantic_index_ready"]:
        plan.append(
            RetrievalTask(
                task_id="search_project_1",
                domain="project",
                tool="search_projects",
                query=query,
                filters=_location_filters(listing_filters),
                retrieved_for=["project_agent"],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    should_search_news = "news_agent" in agents or (
        "investment_advisor" in agents and _needs_news(query)
    )
    if should_search_news and caps["news"]["semantic_index_ready"]:
        plan.append(
            RetrievalTask(
                task_id="search_news_1",
                domain="news",
                tool="search_articles",
                query=query,
                filters={"exclude_category": "legal"},
                retrieved_for=[
                    "news_agent" if "news_agent" in agents else "investment_advisor"
                ],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    should_search_project_for_investment = (
        "investment_advisor" in agents
        and "project_agent" not in agents
        and _needs_project(query)
        and caps["project"]["semantic_index_ready"]
    )
    if should_search_project_for_investment:
        plan.append(
            RetrievalTask(
                task_id="search_project_for_investment_1",
                domain="project",
                tool="search_projects",
                query=query,
                filters=_location_filters(listing_filters),
                retrieved_for=["investment_advisor"],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    return plan
