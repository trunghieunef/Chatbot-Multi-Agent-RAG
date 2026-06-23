"""
LangGraph-based Agentic RAG workflow.

Replaces the pure-Python OrchestratorAgent with a LangGraph StateGraph
that provides: checkpointing (SQLite), streaming, and built-in retry.

Graph structure:
    route (classify + select agents)
      → dispatch_agents (parallel via asyncio)
      → synthesize (merge + safety)

All state is tracked in AgenticState, persisted via SqliteSaver.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from operator import __or__ as union_op
from typing import Annotated, Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent_service.config import get_agent_settings
from agent_service.contracts import (
    AgentChatRequest,
    AgentChatResponse,
    AgentContext,
    AgentResult,
    AgentSource,
    AgentThought,
    AgentAction,
    TraceSummary,
    StructuredWarning,
    ToolDef,
)
from agent_service.graph.blackboard import (
    append_blackboard_entry,
)
from agent_service.graph.router import route_request, RouterDecision
from agent_service.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ── LangGraph State ───────────────────────────────────────────────

class AgenticState(dict):
    """Typed state for the LangGraph agentic workflow.

    Used as the StateGraph state schema. All keys are optional with defaults.
    """
    pass


def _initial_state(request: AgentChatRequest) -> dict[str, Any]:
    return {
        "request": request,
        "router_decision": RouterDecision(intent="unknown", agents=[], mode="rule"),
        "normalized_query": "",
        "routing_filters": {},
        "agent_blackboard": {"entries": []},
        "final_response": "",
        "final_sources": [],
        "final_warnings": [],
        "suggested_actions": [],
        "agents_used": [],
        "_agent_results": {},
    }


# ── Retry wrapper ─────────────────────────────────────────────────

def with_retry(func):
    """Retry a tool call on transient errors with exponential backoff."""

    async def wrapper(*args, **kwargs):
        settings = get_agent_settings()
        max_retries = settings.AGENT_TOOL_RETRY_MAX
        backoff_secs = settings.AGENT_TOOL_RETRY_BACKOFF_SECONDS
        last_error = None
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if attempt < max_retries - 1:
                    wait = backoff_secs * (2 ** attempt)
                    logger.warning(
                        "Tool retry %s/%s after %.1fs: %s",
                        attempt + 1, max_retries, wait, exc,
                    )
                    await asyncio.sleep(wait)
        raise last_error  # type: ignore

    return wrapper


# ── Tool Registry ─────────────────────────────────────────────────

def build_default_tool_registry() -> ToolRegistry:
    """Build ToolRegistry with all tools bound with retry wrappers."""
    from agent_service.tools.retrieval import (
        search_listings, search_projects, search_articles, RetrievalTrace,
    )
    from agent_service.tools.market import lookup_market_metrics, lookup_market_timeseries

    registry = ToolRegistry()

    registry.register(ToolDef(
        name="search_listings",
        description="Tìm kiếm bất động sản theo tiêu chí",
        parameters={
            "query": "str", "filters": "dict", "top_k": "int", "rerank_to": "int",
        },
        required_params=["query"],
        allowed_for=["property_search", "investment_advisor"],
    ))
    registry.register(ToolDef(
        name="search_projects",
        description="Tìm kiếm dự án bất động sản",
        parameters={
            "query": "str", "filters": "dict", "top_k": "int", "rerank_to": "int",
        },
        required_params=["query"],
        allowed_for=["project_agent"],
    ))
    registry.register(ToolDef(
        name="search_articles",
        description="Tìm kiếm bài viết kiến thức (pháp lý, tin tức)",
        parameters={
            "query": "str", "filters": "dict", "top_k": "int", "rerank_to": "int",
        },
        required_params=["query"],
        allowed_for=["legal_advisor", "news_agent"],
    ))
    registry.register(ToolDef(
        name="lookup_market_metrics",
        description="Tra cứu giá trung bình/m² theo khu vực",
        parameters={"filters": "dict"},
        required_params=["filters"],
        allowed_for=["market_analysis", "investment_advisor", "property_search"],
    ))
    registry.register(ToolDef(
        name="lookup_market_timeseries",
        description="Lấy chuỗi thời gian giá bất động sản",
        parameters={"filters": "dict"},
        required_params=["filters"],
        allowed_for=["market_analysis", "investment_advisor"],
    ))

    @with_retry
    async def _search_listings_wrapper(*, query, filters=None, top_k=20, rerank_to=5):
        trace = RetrievalTrace(request_id="agentic")
        results = await search_listings(query=query, filters=filters, trace=trace, top_k=top_k, rerank_to=rerank_to)
        results = await _attach_listing_images(results)
        evidence_ids = [f"ev_{r.get('id', f'listing_{i}')}" for i, r in enumerate(results) if isinstance(r, dict)]
        return {"status": "success", "results": results, "evidence_ids": evidence_ids}

    @with_retry
    async def _search_projects_wrapper(*, query, filters=None, top_k=20, rerank_to=5):
        trace = RetrievalTrace(request_id="agentic")
        results = await search_projects(query=query, filters=filters, trace=trace, top_k=top_k, rerank_to=rerank_to)
        evidence_ids = [f"ev_{r.get('id', f'project_{i}')}" for i, r in enumerate(results) if isinstance(r, dict)]
        return {"status": "success", "results": results, "evidence_ids": evidence_ids}

    @with_retry
    async def _search_articles_wrapper(*, query, filters=None, top_k=20, rerank_to=5):
        trace = RetrievalTrace(request_id="agentic")
        results = await search_articles(query=query, filters=filters, trace=trace, top_k=top_k, rerank_to=rerank_to)
        evidence_ids = [f"ev_{r.get('id', f'article_{i}')}" for i, r in enumerate(results) if isinstance(r, dict)]
        return {"status": "success", "results": results, "evidence_ids": evidence_ids}

    @with_retry
    async def _market_metrics_wrapper(*, filters):
        results = await lookup_market_metrics(filters=filters or {})
        return {"status": "success", "results": results, "evidence_ids": []}

    @with_retry
    async def _market_timeseries_wrapper(*, filters):
        results = await lookup_market_timeseries(filters=filters or {})
        return {"status": "success", "results": results, "evidence_ids": []}

    registry.bind("search_listings", _search_listings_wrapper)
    registry.bind("search_projects", _search_projects_wrapper)
    registry.bind("search_articles", _search_articles_wrapper)
    registry.bind("lookup_market_metrics", _market_metrics_wrapper)
    registry.bind("lookup_market_timeseries", _market_timeseries_wrapper)

    return registry


async def _attach_listing_images(results: list[dict]) -> list[dict]:
    if not results:
        return results
    listing_ids = [r["id"] for r in results if isinstance(r, dict) and r.get("id") is not None]
    if not listing_ids:
        return results
    try:
        from app.database import async_session
        from sqlalchemy import text
        async with async_session() as session:
            rows = await session.execute(
                text("SELECT listing_id, image_url FROM listing_images WHERE listing_id = ANY(:ids) AND sort_order <= 2 ORDER BY listing_id, sort_order"),
                {"ids": listing_ids},
            )
            images_by_id: dict[int, list[str]] = {}
            for row in rows:
                lid, url = row.listing_id, row.image_url
                images_by_id.setdefault(lid, [])
                if len(images_by_id[lid]) < 2:
                    images_by_id[lid].append(url)
    except Exception:
        return results
    for r in results:
        lid = r.get("id")
        if lid in images_by_id and images_by_id[lid]:
            r["images"] = images_by_id[lid]
    return results


_registry: ToolRegistry | None = None


def get_agentic_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = build_default_tool_registry()
    return _registry


# ── Agent Runner ──────────────────────────────────────────────────

def _agent_think(agent_name: str, context: AgentContext, iteration: int, has_results: bool) -> AgentThought:
    """Deterministic think — decides next action based on agent type and state."""
    if agent_name == "property_search":
        if not has_results:
            return AgentThought(iteration=iteration, reasoning="Cần tìm kiếm bất động sản.", action="call_tool",
                tool_name="search_listings",
                tool_params={"query": context.normalized_query, "filters": context.routing_filters, "top_k": 20, "rerank_to": 5},
                confidence=0.9)
        return AgentThought(iteration=iteration, reasoning="Đã có kết quả.", action="final_answer", confidence=0.9)

    if agent_name == "market_analysis":
        if not has_results:
            return AgentThought(iteration=iteration, reasoning="Cần dữ liệu thị trường.", action="call_tool",
                tool_name="lookup_market_metrics", tool_params={"filters": context.routing_filters}, confidence=0.9)
        if iteration == 0:
            return AgentThought(iteration=iteration, reasoning="Cần chuỗi thời gian.", action="call_tool",
                tool_name="lookup_market_timeseries", tool_params={"filters": context.routing_filters}, confidence=0.85)
        return AgentThought(iteration=iteration, reasoning="Đã đủ dữ liệu.", action="final_answer", confidence=0.9)

    if agent_name == "legal_advisor":
        if not has_results:
            return AgentThought(iteration=iteration, reasoning="Cần tra cứu pháp lý.", action="call_tool",
                tool_name="search_articles",
                tool_params={"query": context.normalized_query, "filters": {"category": "legal"}, "top_k": 15, "rerank_to": 5},
                confidence=0.9)
        return AgentThought(iteration=iteration, reasoning="Đã có văn bản.", action="final_answer", confidence=0.85)

    if agent_name == "investment_advisor":
        if not has_results:
            return AgentThought(iteration=iteration, reasoning="Cần dữ liệu thị trường.", action="call_tool",
                tool_name="lookup_market_metrics",
                tool_params={"filters": {"city": context.routing_filters.get("city", "Hồ Chí Minh"), "listing_type": context.routing_filters.get("listing_type", "sale")}},
                confidence=0.8)
        return AgentThought(iteration=iteration, reasoning="Đã có dữ liệu.", action="final_answer", confidence=0.8)

    if agent_name == "project_agent":
        if not has_results:
            return AgentThought(iteration=iteration, reasoning="Cần tìm dự án.", action="call_tool",
                tool_name="search_projects",
                tool_params={"query": context.normalized_query, "filters": context.routing_filters, "top_k": 15, "rerank_to": 5},
                confidence=0.9)
        return AgentThought(iteration=iteration, reasoning="Đã có dữ liệu.", action="final_answer", confidence=0.9)

    if agent_name == "news_agent":
        if not has_results:
            return AgentThought(iteration=iteration, reasoning="Cần tìm tin tức.", action="call_tool",
                tool_name="search_articles",
                tool_params={"query": context.normalized_query, "filters": {"exclude_category": "legal"}, "top_k": 15, "rerank_to": 5},
                confidence=0.9)
        return AgentThought(iteration=iteration, reasoning="Đã có tin tức.", action="final_answer", confidence=0.9)

    return AgentThought(iteration=iteration, reasoning="Done.", action="final_answer", confidence=0.5)


def _agent_build_result(agent_name: str, all_results: list[dict], evidence_ids: list[str], iterations: int) -> AgentResult:
    """Build AgentResult from collected tool results."""
    if not all_results:
        return AgentResult(agent_name=agent_name, status="no_evidence",
            content="Chưa tìm thấy dữ liệu phù hợp.", evidence_ids_used=evidence_ids, iterations=iterations)

    if agent_name == "property_search":
        lines = ["🏠 **Kết quả tìm kiếm bất động sản:**\n"]
        for i, item in enumerate(all_results[:10], 1):
            title = item.get("title", "N/A")
            price = item.get("price_text", "Liên hệ")
            area = item.get("area_text", "N/A")
            district = item.get("district", "")
            city = item.get("city", "")
            loc = f"{district}, {city}" if district else city
            lines.append(f"**{i}. {title}**\n   💰 {price} | 📐 {area} | 📍 {loc}\n")
        content = "\n".join(lines)

    elif agent_name == "market_analysis":
        lines = ["📊 **Phân tích thị trường:**\n"]
        for m in [r for r in all_results if r.get("metric")][:5]:
            loc = m.get("location", {})
            d = loc.get("district", "") if isinstance(loc, dict) else ""
            lines.append(f"- {d or 'KV'}: {m.get('value','N/A')} {m.get('unit','tr/m²')}")
        content = "\n".join(lines) + "\n\n> ℹ️ Dữ liệu tham khảo."

    elif agent_name == "legal_advisor":
        lines = ["⚖️ **Tư vấn pháp lý:**\n"]
        for i, a in enumerate(all_results[:5], 1):
            lines.append(f"**{i}. {a.get('title','Văn bản')}**")
            if a.get("snippet"):
                lines.append(f"   {a['snippet'][:300]}")
            lines.append("")
        lines.append("> ⚠️ Thông tin tham khảo, không thay thế luật sư.")
        content = "\n".join(lines)

    elif agent_name == "investment_advisor":
        content = ("💰 **Phân tích đầu tư:**\n\n- Tiềm năng: xem xét vị trí, quy hoạch.\n"
                   "- Rủi ro: thanh khoản, pháp lý.\n\n"
                   "> ⚠️ Không phải lời khuyên tài chính.")

    elif agent_name == "project_agent":
        lines = ["🏗️ **Thông tin dự án:**\n"]
        for i, p in enumerate(all_results[:5], 1):
            lines.append(f"**{i}. {p.get('title','Dự án')}**")
            lines.append(f"   🏢 {p.get('developer','Chưa rõ CĐT')}\n")
        content = "\n".join(lines)

    elif agent_name == "news_agent":
        lines = ["📰 **Tin tức bất động sản:**\n"]
        for i, a in enumerate(all_results[:5], 1):
            lines.append(f"**{i}. {a.get('title','Bài viết')}**")
            if a.get("snippet"):
                lines.append(f"   {a['snippet'][:200]}")
            lines.append("")
        content = "\n".join(lines)

    else:
        content = f"Kết quả từ {agent_name}: {len(all_results)} mục."

    sources = [
        AgentSource(type="listing", id=item.get("id"), title=item.get("title"), snippet=item.get("snippet", ""))
        for item in all_results[:10] if isinstance(item, dict)
    ]

    return AgentResult(agent_name=agent_name, status="completed", content=content,
        evidence_ids_used=evidence_ids, sources=sources, confidence="medium", iterations=iterations)


async def _run_single_agent(agent_name: str, state: dict[str, Any], registry: ToolRegistry) -> AgentResult:
    """Run one agent's ReAct loop."""
    settings = get_agent_settings()
    max_iter = settings.AGENT_MAX_ITERATIONS
    request = state["request"]
    context = AgentContext(
        agent_name=agent_name, query=request.message,
        normalized_query=state.get("normalized_query", request.message.lower()),
        routing_filters=state.get("routing_filters", {}),
        user_preferences=request.user_preferences, locale=request.locale,
    )

    all_results: list[dict[str, Any]] = []
    all_evidence_ids: list[str] = []
    iterations = 0

    for iteration in range(max_iter):
        iterations = iteration + 1
        thought = _agent_think(agent_name, context, iteration, len(all_results) > 0)

        if thought.action == "final_answer":
            break
        if thought.action == "ask_clarification":
            return AgentResult(agent_name=agent_name, status="partial",
                content=thought.clarifying_question or "Vui lòng cung cấp thêm chi tiết.", iterations=iterations)

        try:
            result = await registry.call(tool_name=thought.tool_name or "", agent_name=agent_name, **thought.tool_params)
        except Exception as exc:
            logger.warning("Agent %s tool call failed: %s", agent_name, exc)
            continue

        items = result.get("results", [])
        if isinstance(items, list):
            all_results.extend(items)
        for eid in result.get("evidence_ids", []):
            if eid not in all_evidence_ids:
                all_evidence_ids.append(eid)

        if all_results:
            break

    return _agent_build_result(agent_name, all_results, all_evidence_ids, iterations)


# ── LangGraph Nodes ───────────────────────────────────────────────

async def _node_route(state: dict[str, Any]) -> dict[str, Any]:
    request = state["request"]
    if not request.message.strip():
        return {
            "router_decision": RouterDecision(intent="general", agents=[], mode="rule"),
            "normalized_query": "", "routing_filters": {}, "agents_used": [],
        }
    decision = await route_request({"request": request})
    return {
        "router_decision": decision,
        "normalized_query": request.message.lower(),
        "routing_filters": decision.filters,
        "agents_used": decision.agents if not decision.needs_clarification else [],
    }


def _route_after_route(state: dict[str, Any]) -> str:
    decision = state.get("router_decision")
    if decision is None:
        return "synthesize"
    if decision.needs_clarification or not decision.agents:
        return "synthesize"
    return "dispatch_agents"


async def _node_dispatch_agents(state: dict[str, Any]) -> dict[str, Any]:
    decision = state["router_decision"]
    agents_to_run = decision.agents
    registry = get_agentic_registry()

    tasks = [_run_single_agent(name, state, registry) for name in agents_to_run]
    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    agent_results: dict[str, Any] = {}
    for i, result in enumerate(results_list):
        name = agents_to_run[i] if i < len(agents_to_run) else f"agent_{i}"
        if isinstance(result, BaseException):
            agent_results[name] = AgentResult(agent_name=name, status="failed", content=f"Error: {result}").model_dump(mode="python")
        elif isinstance(result, AgentResult):
            agent_results[name] = result.model_dump(mode="python")
            # Write to blackboard
            if result.content:
                bb = append_blackboard_entry(state, author=name, entry_type=f"{name}_analysis",
                    content=result.content[:1000], evidence_ids=result.evidence_ids_used,
                    confidence="medium", step_name="dispatch")
                state["agent_blackboard"] = bb.get("agent_blackboard", state.get("agent_blackboard", {}))

    return {"_agent_results": agent_results, "agent_blackboard": state.get("agent_blackboard", {})}


async def _node_synthesize(state: dict[str, Any]) -> dict[str, Any]:
    decision = state.get("router_decision")
    agents_used = state.get("agents_used", [])
    raw_results = state.get("_agent_results", {})

    if decision and decision.needs_clarification:
        return {"final_response": decision.clarifying_question or "Bạn có thể bổ sung tiêu chí không?",
                "final_sources": [], "final_warnings": [], "suggested_actions": ["Bổ sung ngân sách", "Bổ sung khu vực"]}

    if not agents_used:
        return {"final_response": "Xin chào! Tôi có thể giúp bạn tìm kiếm bất động sản, phân tích thị trường, hoặc tư vấn pháp lý. Bạn muốn tìm hiểu về vấn đề gì?",
                "final_sources": [], "final_warnings": [], "suggested_actions": ["Tìm bất động sản", "Phân tích thị trường", "Tư vấn pháp lý"]}

    parts: list[str] = []
    all_sources: list[AgentSource] = []
    for name in agents_used:
        rd = raw_results.get(name, {})
        content = rd.get("content", "")
        if content:
            parts.append(content)
        for src in rd.get("sources", []):
            if isinstance(src, dict):
                all_sources.append(AgentSource(**src))

    final = "\n\n".join(parts) if parts else "Xin lỗi, chưa thể xử lý yêu cầu này."

    if "legal_advisor" in agents_used and "không thay thế tư vấn luật sư" not in final.lower():
        final += "\n\n> ⚠️ Thông tin pháp lý chỉ mang tính tham khảo, không thay thế tư vấn luật sư."
    if "investment_advisor" in agents_used and "không phải lời khuyên tài chính" not in final.lower():
        final += "\n\n> ⚠️ Đây không phải lời khuyên tài chính."

    suggestions: list[str] = []
    if "property_search" in agents_used:
        suggestions.extend(["So sánh các lựa chọn", "Hỏi thêm về pháp lý"])
    if "market_analysis" in agents_used:
        suggestions.append("Xem xu hướng khu vực khác")
    if "investment_advisor" in agents_used:
        suggestions.extend(["Xác nhận ngân sách", "Kiểm tra pháp lý"])
    if not suggestions:
        suggestions = ["Tìm bất động sản", "Phân tích thị trường", "Tư vấn pháp lý"]

    return {"final_response": final, "final_sources": list({s.id: s for s in all_sources if s.id}.values()),
            "final_warnings": [], "suggested_actions": suggestions[:5]}


# ── Graph Builder ─────────────────────────────────────────────────

def build_agentic_graph() -> CompiledStateGraph:
    """Build StateGraph: route → dispatch_agents → synthesize + SQLite checkpoint."""
    graph = StateGraph(dict)

    graph.add_node("route", _node_route)
    graph.add_node("dispatch_agents", _node_dispatch_agents)
    graph.add_node("synthesize", _node_synthesize)

    graph.set_entry_point("route")
    graph.add_conditional_edges("route", _route_after_route, {"dispatch_agents": "dispatch_agents", "synthesize": "synthesize"})
    graph.add_edge("dispatch_agents", "synthesize")
    graph.add_edge("synthesize", END)

    settings = get_agent_settings()
    checkpointer = None
    if settings.AGENT_CHECKPOINT_ENABLED:
        checkpointer = MemorySaver()

    return graph.compile(checkpointer=checkpointer)


_compiled_graph: CompiledStateGraph | None = None


def get_agentic_graph() -> CompiledStateGraph:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_agentic_graph()
    return _compiled_graph


# ── Entry Points ──────────────────────────────────────────────────

async def run_agentic_graph(request: AgentChatRequest) -> AgentChatResponse:
    """Run full agentic graph, return complete response."""
    settings = get_agent_settings()
    started = time.perf_counter()
    graph = get_agentic_graph()

    config = {"configurable": {"thread_id": request.session_id, "checkpoint_ns": "agentic_chat"}}
    initial = _initial_state(request)

    final_state = await graph.ainvoke(initial, config)

    router_decision = final_state.get("router_decision")
    if isinstance(router_decision, RouterDecision):
        intent = router_decision.intent
    else:
        intent = "unknown"

    return AgentChatResponse(
        request_id=request.request_id,
        final_response=final_state.get("final_response", ""),
        agents_used=final_state.get("agents_used", []),
        sources=final_state.get("final_sources", []),
        suggested_actions=final_state.get("suggested_actions", []),
        trace_summary=TraceSummary(
            intent=intent,
            agents=final_state.get("agents_used", []),
            source_count=len(final_state.get("final_sources", [])),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        ),
        full_trace={"graph_version": settings.AGENT_GRAPH_VERSION, "mode": "langgraph_state_graph"},
    )


async def run_agentic_graph_stream(request: AgentChatRequest):
    """Run agentic graph with streaming — yields SSE events per node.

    Events:
        {event: "node_start", node: str, status: str}
        {event: "node_complete", node: str, duration_ms: float}
        {event: "final", request_id: str, payload: AgentChatResponse}
        {event: "error", request_id: str, payload: {code, message}}
    """
    settings = get_agent_settings()
    started = time.perf_counter()
    graph = get_agentic_graph()
    config = {"configurable": {"thread_id": request.session_id, "checkpoint_ns": "agentic_chat"}}
    initial = _initial_state(request)

    NODE_STATUS: dict[str, str] = {
        "route": "đang phân tích câu hỏi...",
        "dispatch_agents": "đang tìm kiếm và phân tích dữ liệu...",
        "synthesize": "đang tổng hợp kết quả...",
    }
    node_started: dict[str, float] = {}

    try:
        async for event in graph.astream(initial, config, stream_mode="updates"):
            for node_name, node_output in event.items():
                now = time.perf_counter()
                if node_name not in node_started:
                    node_started[node_name] = now
                    yield {"event": "node_start", "node": node_name, "status": NODE_STATUS.get(node_name, f"xử lý {node_name}..."), "payload": {}}
                yield {"event": "node_complete", "node": node_name,
                    "duration_ms": round((now - node_started.get(node_name, now)) * 1000, 2),
                    "payload": {k: v for k, v in (node_output or {}).items() if k in ("agents_used", "suggested_actions")}}

        final_state = await graph.aget_state(config)
        vs = final_state.values if final_state.values else {}
        response = AgentChatResponse(
            request_id=request.request_id,
            final_response=vs.get("final_response", ""),
            agents_used=vs.get("agents_used", []),
            sources=vs.get("final_sources", []),
            suggested_actions=vs.get("suggested_actions", []),
            trace_summary=TraceSummary(intent="streaming", agents=vs.get("agents_used", []),
                source_count=len(vs.get("final_sources", [])), latency_ms=round((time.perf_counter() - started) * 1000, 2)),
            full_trace={"graph_version": settings.AGENT_GRAPH_VERSION, "streaming": True},
        )
        yield {"event": "final", "request_id": request.request_id, "payload": response.model_dump(mode="json")}

    except Exception as exc:
        logger.exception("Agentic stream failed")
        yield {"event": "error", "request_id": request.request_id, "payload": {"code": "graph_stream_error", "message": str(exc)}}
