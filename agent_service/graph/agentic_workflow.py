from __future__ import annotations

from typing import Any

from agent_service.agents.orchestrator import OrchestratorAgent
from agent_service.config import get_agent_settings
from agent_service.contracts import (
    AgentChatRequest,
    AgentChatResponse,
)
from agent_service.tools.registry import ToolRegistry, ToolDef


def build_default_tool_registry() -> ToolRegistry:
    """Build ToolRegistry with all available tools and bindings.

    Each tool is registered with its metadata (ToolDef) and
    bound to the actual async function from agent_service/tools/.

    Imports are lazy (inside this function) to avoid dependency
    chain issues when the module is first loaded.
    """
    from agent_service.tools.retrieval import (
        search_listings,
        search_projects,
        search_articles,
        RetrievalTrace,
    )
    from agent_service.tools.market import lookup_market_metrics, lookup_market_timeseries


def build_default_tool_registry() -> ToolRegistry:
    """Build ToolRegistry with all available tools and bindings.

    Each tool is registered with its metadata (ToolDef) and
    bound to the actual async function from agent_service/tools/.
    """
    registry = ToolRegistry()

    # ── Retrieval tools ──────────────────────────────────────
    registry.register(ToolDef(
        name="search_listings",
        description="Tìm kiếm bất động sản theo tiêu chí (giá, diện tích, khu vực, loại hình)",
        parameters={
            "query": "str - Từ khóa tìm kiếm",
            "filters": "dict - Bộ lọc: city, district, property_type, min_price, max_price, listing_type",
            "top_k": "int - Số lượng kết quả tối đa (default: 20)",
            "rerank_to": "int - Số lượng sau rerank (default: 5)",
        },
        required_params=["query"],
        allowed_for=["property_search", "investment_advisor"],
    ))

    registry.register(ToolDef(
        name="search_projects",
        description="Tìm kiếm dự án bất động sản theo tên, chủ đầu tư, khu vực",
        parameters={
            "query": "str - Từ khóa tìm kiếm",
            "filters": "dict - Bộ lọc: city, district, developer",
            "top_k": "int - Số lượng kết quả (default: 20)",
            "rerank_to": "int - Số lượng sau rerank (default: 5)",
        },
        required_params=["query"],
        allowed_for=["project_agent"],
    ))

    registry.register(ToolDef(
        name="search_articles",
        description="Tìm kiếm bài viết kiến thức (pháp lý, tin tức, hướng dẫn)",
        parameters={
            "query": "str - Từ khóa tìm kiếm",
            "filters": "dict - Bộ lọc: category (legal/news), exclude_category",
            "top_k": "int - Số lượng kết quả (default: 20)",
            "rerank_to": "int - Số lượng sau rerank (default: 5)",
        },
        required_params=["query"],
        allowed_for=["legal_advisor", "news_agent"],
    ))

    # ── Market tools ─────────────────────────────────────────
    registry.register(ToolDef(
        name="lookup_market_metrics",
        description="Tra cứu chỉ số thị trường hiện tại: giá trung bình/m², số lượng listing theo khu vực",
        parameters={
            "filters": "dict - city, district, property_type, listing_type",
        },
        required_params=["filters"],
        allowed_for=["market_analysis", "investment_advisor", "property_search"],
    ))

    registry.register(ToolDef(
        name="lookup_market_timeseries",
        description="Lấy dữ liệu chuỗi thời gian giá bất động sản theo tháng",
        parameters={
            "filters": "dict - city, district, property_type, listing_type",
        },
        required_params=["filters"],
        allowed_for=["market_analysis", "investment_advisor"],
    ))

    # ── Bind tool functions ──────────────────────────────────
    async def _search_listings_wrapper(*, query, filters=None, top_k=20, rerank_to=5):
        trace = RetrievalTrace(request_id="agentic")
        results = await search_listings(
            query=query, filters=filters, trace=trace,
            top_k=top_k, rerank_to=rerank_to,
        )
        evidence_ids = [
            f"ev_{r.get('id', f'listing_{i}')}"
            for i, r in enumerate(results) if isinstance(r, dict)
        ]
        return {"status": "success", "results": results, "evidence_ids": evidence_ids}

    async def _search_projects_wrapper(*, query, filters=None, top_k=20, rerank_to=5):
        trace = RetrievalTrace(request_id="agentic")
        results = await search_projects(
            query=query, filters=filters, trace=trace,
            top_k=top_k, rerank_to=rerank_to,
        )
        evidence_ids = [
            f"ev_{r.get('id', f'project_{i}')}"
            for i, r in enumerate(results) if isinstance(r, dict)
        ]
        return {"status": "success", "results": results, "evidence_ids": evidence_ids}

    async def _search_articles_wrapper(*, query, filters=None, top_k=20, rerank_to=5):
        trace = RetrievalTrace(request_id="agentic")
        results = await search_articles(
            query=query, filters=filters, trace=trace,
            top_k=top_k, rerank_to=rerank_to,
        )
        evidence_ids = [
            f"ev_{r.get('id', f'article_{i}')}"
            for i, r in enumerate(results) if isinstance(r, dict)
        ]
        return {"status": "success", "results": results, "evidence_ids": evidence_ids}

    async def _market_metrics_wrapper(*, filters):
        results = await lookup_market_metrics(filters=filters or {})
        return {"status": "success", "results": results, "evidence_ids": []}

    async def _market_timeseries_wrapper(*, filters):
        results = await lookup_market_timeseries(filters=filters or {})
        return {"status": "success", "results": results, "evidence_ids": []}

    registry.bind("search_listings", _search_listings_wrapper)
    registry.bind("search_projects", _search_projects_wrapper)
    registry.bind("search_articles", _search_articles_wrapper)
    registry.bind("lookup_market_metrics", _market_metrics_wrapper)
    registry.bind("lookup_market_timeseries", _market_timeseries_wrapper)

    return registry


# Singleton registry
_agentic_registry: ToolRegistry | None = None


def get_agentic_registry() -> ToolRegistry:
    global _agentic_registry
    if _agentic_registry is None:
        _agentic_registry = build_default_tool_registry()
    return _agentic_registry


async def run_agentic_graph(request: AgentChatRequest) -> AgentChatResponse:
    """Entry point for agentic RAG — replaces run_agent_graph().

    This is a thin wrapper that creates the OrchestratorAgent
    with the default ToolRegistry and delegates to it.
    """
    settings = get_agent_settings()
    registry = get_agentic_registry()
    orchestrator = OrchestratorAgent(
        tool_registry=registry,
        max_agent_iterations=settings.AGENT_REACT_MAX_ITERATIONS,
        use_llm=settings.AGENT_SPECIALIST_LLM_ENABLED,
    )
    return await orchestrator.run(request)
