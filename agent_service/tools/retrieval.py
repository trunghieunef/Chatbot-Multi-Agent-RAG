from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

from app.services.rag.hybrid_search import hybrid_search


@dataclass
class RetrievalTrace:
    request_id: str
    events: list[dict[str, Any]] = field(default_factory=list)

    def add_event(
        self,
        *,
        tool_name: str,
        parent_type: str,
        filters: dict[str, Any] | None,
        result_count: int,
        latency_ms: float,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        self.events.append(
            {
                "request_id": self.request_id,
                "tool_name": tool_name,
                "parent_type": parent_type,
                "filters": filters or {},
                "result_count": result_count,
                "latency_ms": latency_ms,
                "status": status,
                "error_message": error_message,
            }
        )


async def _run_hybrid_tool(
    *,
    query: str,
    filters: dict[str, Any] | None,
    trace: RetrievalTrace,
    tool_name: str,
    parent_type: str,
    top_k: int = 20,
    rerank_to: int = 5,
) -> list[dict[str, Any]]:
    started = time.perf_counter()
    try:
        results = await hybrid_search(
            query=query,
            filters=filters,
            parent_type=parent_type,
            top_k=top_k,
            rerank_to=rerank_to,
        )
    except Exception as exc:
        trace.add_event(
            tool_name=tool_name,
            parent_type=parent_type,
            filters=filters,
            result_count=0,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            status="error",
            error_message=str(exc),
        )
        return []

    trace.add_event(
        tool_name=tool_name,
        parent_type=parent_type,
        filters=filters,
        result_count=len(results),
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
        status="success",
    )
    return results


async def search_listings(
    query: str,
    filters: dict[str, Any] | None,
    trace: RetrievalTrace,
    *,
    top_k: int = 20,
    rerank_to: int = 5,
) -> list[dict[str, Any]]:
    return await _run_hybrid_tool(
        query=query,
        filters=filters,
        trace=trace,
        tool_name="search_listings",
        parent_type="listing",
        top_k=top_k,
        rerank_to=rerank_to,
    )


async def search_projects(
    query: str,
    filters: dict[str, Any] | None,
    trace: RetrievalTrace,
    *,
    top_k: int = 20,
    rerank_to: int = 5,
) -> list[dict[str, Any]]:
    return await _run_hybrid_tool(
        query=query,
        filters=filters,
        trace=trace,
        tool_name="search_projects",
        parent_type="project",
        top_k=top_k,
        rerank_to=rerank_to,
    )


async def search_articles(
    query: str,
    filters: dict[str, Any] | None,
    trace: RetrievalTrace,
    *,
    top_k: int = 20,
    rerank_to: int = 5,
) -> list[dict[str, Any]]:
    return await _run_hybrid_tool(
        query=query,
        filters=filters,
        trace=trace,
        tool_name="search_articles",
        parent_type="article",
        top_k=top_k,
        rerank_to=rerank_to,
    )
