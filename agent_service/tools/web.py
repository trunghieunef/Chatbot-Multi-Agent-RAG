"""Web search tool (Tavily) — fallback evidence when the internal KB is empty.

Results are shaped like article records (title/url/snippet/citation) so the
news/legal agents' existing build_result code renders them unchanged.
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx

from agent_service.config import get_agent_settings

_TAVILY_URL = "https://api.tavily.com/search"


def _shape_result(item: dict[str, Any]) -> dict[str, Any]:
    url = item.get("url") or ""
    return {
        "title": item.get("title") or url,
        "url": url,
        "snippet": (item.get("content") or "")[:300],
        "citation": url,
        "source": "web",
        "score": item.get("score"),
    }


async def search_web(
    query: str,
    *,
    max_results: int = 5,
    api_key: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Search the web via Tavily. Degrades to a skipped result without a key."""
    key = api_key if api_key is not None else get_agent_settings().TAVILY_API_KEY
    if not key:
        return {"status": "skipped", "results": [], "evidence_ids": [],
                "skipped_reason": "no_tavily_api_key"}

    payload = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    }
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=10)
    try:
        response = await http.post(_TAVILY_URL, json=payload)
        response.raise_for_status()
        data = response.json()
    finally:
        if own_client:
            await http.aclose()

    raw = data.get("results") or []
    results = [_shape_result(item) for item in raw if isinstance(item, dict)]
    run_id = uuid.uuid4().hex[:6]
    evidence_ids = [f"ev_web_{run_id}_{i}" for i in range(len(results))]
    for record, evidence_id in zip(results, evidence_ids, strict=True):
        record["evidence_id"] = evidence_id
    return {"status": "success", "results": results, "evidence_ids": evidence_ids}
