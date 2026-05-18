"""Intent routing for the production chatbot pipeline."""

from __future__ import annotations

import json
import re
import unicodedata

from app.config import get_settings
from app.services.chatbot.contracts import RoutingDecision
from app.services.rag.simple_rag import extract_search_filters


AGENT_ORDER = ["legal_advisor", "investment_advisor", "market_analysis", "property_search"]


def normalize_query(query: str) -> str:
    """Return lowercase Vietnamese text without accents for keyword matching."""
    normalized = unicodedata.normalize("NFD", query or "")
    without_accents = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return without_accents.lower()


def _extract_additional_filters(normalized: str) -> dict[str, object]:
    filters: dict[str, object] = {}
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


def _keyword_route(query: str) -> RoutingDecision:
    normalized = normalize_query(query)
    filters = extract_search_filters(query)
    filters.update(_extract_additional_filters(normalized))
    target_agents: list[str] = []

    if any(term in normalized for term in ["phap ly", "luat", "thu tuc", "cong chung", "hop dong", "so do", "sang ten"]):
        target_agents.append("legal_advisor")
    if any(term in normalized for term in ["dau tu", "roi", "loi nhuan", "sinh loi", "rental yield", "cho thue lai"]):
        target_agents.append("investment_advisor")
    if any(term in normalized for term in ["thi truong", "xu huong", "bien dong", "thong ke", "gia trung binh"]):
        target_agents.append("market_analysis")
    strong_property_signal = any(
        term in normalized
        for term in ["tim", "can ho", "chung cu", "nha dat", "dat nen", "quan ", "duoi", "toi da", "phong"]
    )
    generic_property_signal = any(term in normalized for term in ["mua", "ban", "thue", "nha", "dat"])
    if strong_property_signal or (not target_agents and generic_property_signal):
        target_agents.append("property_search")

    if not target_agents:
        target_agents.append("property_search")

    ordered_agents = [agent for agent in AGENT_ORDER if agent in set(target_agents)]
    intent = ordered_agents[0].replace("_advisor", "_advice") if len(ordered_agents) == 1 else "mixed"
    if ordered_agents == ["property_search"]:
        intent = "property_search"
    if ordered_agents == ["market_analysis"]:
        intent = "market_analysis"
    return RoutingDecision(intent=intent, target_agents=ordered_agents, search_filters=filters)


def route_query(query: str) -> RoutingDecision:
    """Route a user query to one or more specialized agents."""
    settings = get_settings()
    if not settings.GEMINI_API_KEY:
        return _keyword_route(query)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=(
                "Classify this Vietnamese real-estate query. Return JSON only with "
                "intent, target_agents, and search_filters. Valid target_agents are "
                f"{AGENT_ORDER}. Query: {query}"
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        data = json.loads(response.text or "{}")
        target_agents = [
            agent for agent in AGENT_ORDER if agent in set(data.get("target_agents") or [])
        ]
        if not target_agents:
            return _keyword_route(query)
        filters = extract_search_filters(query)
        filters.update(data.get("search_filters") or {})
        filters.update(_extract_additional_filters(normalize_query(query)))
        intent = data.get("intent") or ("mixed" if len(target_agents) > 1 else target_agents[0])
        return RoutingDecision(intent=intent, target_agents=target_agents, search_filters=filters)
    except Exception:
        return _keyword_route(query)
