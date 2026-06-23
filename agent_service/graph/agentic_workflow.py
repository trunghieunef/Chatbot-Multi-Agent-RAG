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
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from agent_service.agents.fc_runner import run_specialist
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
from agent_service.graph.router import route_request, RouterDecision
from agent_service.graph.synthesis import synthesize_final_answer
from agent_service.llm.gemini import GeminiClient
from agent_service.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ── LangGraph State ───────────────────────────────────────────────

def _merge_dicts(a: dict, b: dict) -> dict:
    """Reducer for keys written concurrently by parallel ``Send`` branches."""
    return {**(a or {}), **(b or {})}


class GraphState(TypedDict, total=False):
    request: Any
    conversation_context: list
    supervisor_plan: dict
    routing_filters: dict
    agents_used: list
    _agent_results: Annotated[dict, _merge_dicts]
    evidence_by_id: Annotated[dict, _merge_dicts]
    final_response: str
    final_sources: list
    suggested_actions: list


def _conversation_context(request: AgentChatRequest) -> list[dict[str, str]]:
    return [
        {"role": item.role, "content": item.content}
        for item in request.conversation_context
    ]


def _initial_state(request: AgentChatRequest) -> dict[str, Any]:
    return {
        "request": request,
        "conversation_context": _conversation_context(request),
        "supervisor_plan": {},
        "routing_filters": {},
        "agents_used": [],
        "_agent_results": {},
        "evidence_by_id": {},
        "final_response": "",
        "final_sources": [],
        "suggested_actions": [],
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


# ── LLM client + supervisor/specialist/synthesize nodes ───────────

def _make_llm_client(settings) -> GeminiClient | None:
    if not settings.GEMINI_API_KEY:
        return None
    return GeminiClient()


async def _node_supervisor(state: dict[str, Any]) -> dict[str, Any]:
    request = state["request"]
    if not request.message.strip():
        return {"supervisor_plan": {"selected_agents": [], "needs_clarification": False,
                                    "intent": "general", "filters": {}},
                "agents_used": []}
    decision = await route_request({
        "request": request,
        "conversation_context": state.get("conversation_context", []),
        "normalized_query": request.message.lower(),
    })
    plan = decision.model_dump(mode="python")
    plan["selected_agents"] = decision.agents
    return {
        "supervisor_plan": plan,
        "routing_filters": decision.filters,
        "agents_used": decision.agents if not decision.needs_clarification else [],
    }


def _dispatch(state: dict[str, Any]):
    plan = state.get("supervisor_plan") or {}
    if plan.get("needs_clarification") or not plan.get("selected_agents"):
        return "synthesize"
    return [Send("specialist", {"agent_name": name, **state})
            for name in plan["selected_agents"]]


async def _node_specialist(state: dict[str, Any]) -> dict[str, Any]:
    agent_name = state["agent_name"]
    request = state["request"]
    settings = get_agent_settings()
    registry = get_agentic_registry()
    context = AgentContext(
        agent_name=agent_name, query=request.message,
        normalized_query=request.message.lower(),
        routing_filters=state.get("routing_filters", {}),
        conversation_context=state.get("conversation_context", []),
        user_preferences=request.user_preferences, locale=request.locale,
    )
    result = await run_specialist(
        agent_name=agent_name, context=context, registry=registry,
        llm_client=_make_llm_client(settings), settings=settings,
    )
    rd = result.model_dump(mode="python")
    evidence = {eid: {"agent": agent_name} for eid in result.evidence_ids_used}
    return {"_agent_results": {agent_name: rd}, "evidence_by_id": evidence}


async def _node_synthesize(state: dict[str, Any]) -> dict[str, Any]:
    plan = state.get("supervisor_plan") or {}
    raw_results = state.get("_agent_results", {})
    agents_used = [a for a in plan.get("selected_agents", []) if a in raw_results]
    settings = get_agent_settings()

    if plan.get("needs_clarification"):
        return {"final_response": plan.get("clarifying_question")
                or "Bạn có thể bổ sung tiêu chí không?",
                "final_sources": [], "suggested_actions": ["Bổ sung ngân sách", "Bổ sung khu vực"]}
    if not agents_used:
        return {"final_response": "Xin chào! Tôi có thể giúp bạn tìm bất động sản, phân tích thị "
                "trường, hoặc tư vấn pháp lý. Bạn muốn tìm hiểu vấn đề gì?",
                "final_sources": [], "suggested_actions":
                ["Tìm bất động sản", "Phân tích thị trường", "Tư vấn pháp lý"]}

    # Collect sources (cards) + evidence.
    all_sources: list[AgentSource] = []
    deterministic_parts: list[str] = []
    for name in agents_used:
        rd = raw_results.get(name, {})
        if rd.get("content"):
            deterministic_parts.append(rd["content"])
        for src in rd.get("sources", []):
            if isinstance(src, dict):
                all_sources.append(AgentSource(**src))
    deterministic_response = "\n\n".join(deterministic_parts) or "Xin lỗi, chưa thể xử lý yêu cầu này."
    allowed_evidence_ids = set(state.get("evidence_by_id", {}).keys())

    llm_client = _make_llm_client(settings)
    generate_json = llm_client.generate_json if llm_client else None
    synth = await synthesize_final_answer(
        query=state["request"].message,
        conversation_context=state.get("conversation_context", []),
        agent_results=raw_results,
        deterministic_response=deterministic_response,
        default_actions=["Tìm bất động sản", "Phân tích thị trường", "Tư vấn pháp lý"],
        generate_json=generate_json,
        timeout_seconds=settings.AGENT_LLM_TIMEOUT_SECONDS,
        allowed_evidence_ids=allowed_evidence_ids,
        supervisor_plan=plan,
        evidence_by_id=state.get("evidence_by_id", {}),
    )

    final = synth.final_response
    if "legal_advisor" in agents_used and "không thay thế tư vấn luật sư" not in final.lower():
        final += "\n\n> ⚠️ Thông tin pháp lý chỉ mang tính tham khảo, không thay thế tư vấn luật sư."
    if "investment_advisor" in agents_used and "không phải lời khuyên tài chính" not in final.lower():
        final += "\n\n> ⚠️ Đây không phải lời khuyên tài chính."

    deduped = list({(s.type, s.id or s.url or s.title): s for s in all_sources}.values())
    return {"final_response": final, "final_sources": deduped,
            "suggested_actions": synth.suggested_actions[:5]}


# ── Graph Builder ─────────────────────────────────────────────────

def _new_state_graph() -> StateGraph:
    """Build the uncompiled supervisor → specialist → synthesize StateGraph."""
    graph = StateGraph(GraphState)
    graph.add_node("supervisor", _node_supervisor)
    graph.add_node("specialist", _node_specialist)
    graph.add_node("synthesize", _node_synthesize)
    graph.set_entry_point("supervisor")
    graph.add_conditional_edges("supervisor", _dispatch, ["specialist", "synthesize"])
    graph.add_edge("specialist", "synthesize")
    graph.add_edge("synthesize", END)
    return graph


def build_agentic_graph(checkpointer=None) -> CompiledStateGraph:
    """Compile the agentic graph (optionally with a checkpointer).

    Sync callers get a checkpointer-free graph by default. This is correct:
    ``run_agentic_graph`` reads its result from the ``ainvoke`` return value,
    not ``aget_state``. The SQLite checkpointer is wired lazily inside the
    async entrypoint via :func:`_get_async_graph`, where a live event loop is
    available to construct the aiosqlite connection cleanly.
    """
    return _new_state_graph().compile(checkpointer=checkpointer)


async def _build_async_checkpointer(settings):
    """Construct a live AsyncSqliteSaver in the current event loop, or None.

    NOTE: disabled by default. ``AsyncSqliteSaver`` wraps an aiosqlite
    connection plus an ``asyncio.Lock`` bound to the loop it was created on.
    Reusing a process-cached saver from another event loop raises
    ``RuntimeError: ... bound to a different event loop``; building a fresh
    file-backed saver per loop instead deadlocks on the shared sqlite file's
    lock. Because the graph is correct WITHOUT a checkpointer — the
    non-streaming entry reads its result from the ``ainvoke`` return value, not
    ``aget_state`` — we fall back to ``checkpointer=None`` to guarantee the
    singleton graph never raises or hangs at runtime. The constructor below is
    retained for reference / future single-loop deployments and is gated behind
    ``AGENT_CHECKPOINT_SQLITE`` (defaults off).
    """
    if not (settings.AGENT_CHECKPOINT_ENABLED
            and getattr(settings, "AGENT_CHECKPOINT_SQLITE", False)):
        return None
    try:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        path = settings.AGENT_CHECKPOINT_PATH
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        conn = await aiosqlite.connect(path)
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        return saver
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("AsyncSqliteSaver unavailable, running without checkpointer: %s", exc)
        return None


_compiled_graph: CompiledStateGraph | None = None
# Cache the async graph PER event loop. Even checkpointer-free this is safe, and
# it leaves room to attach a loop-bound saver should one be enabled later.
_async_graph_by_loop: dict[int, CompiledStateGraph] = {}


def get_agentic_graph() -> CompiledStateGraph:
    """Sync accessor — returns a checkpointer-free compiled graph singleton."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_agentic_graph(checkpointer=None)
    return _compiled_graph


async def _get_async_graph() -> CompiledStateGraph:
    """Async accessor — compiles once per event loop.

    Reads its result from the ``ainvoke`` return value, so the graph is correct
    even though no checkpointer is wired by default (see
    :func:`_build_async_checkpointer`).
    """
    loop_key = id(asyncio.get_running_loop())
    graph = _async_graph_by_loop.get(loop_key)
    if graph is None:
        settings = get_agent_settings()
        checkpointer = await _build_async_checkpointer(settings)
        graph = build_agentic_graph(checkpointer=checkpointer)
        _async_graph_by_loop[loop_key] = graph
    return graph


# ── Entry Points ──────────────────────────────────────────────────

async def run_agentic_graph(request: AgentChatRequest) -> AgentChatResponse:
    """Run full agentic graph, reading the result from the ainvoke return."""
    settings = get_agent_settings()
    started = time.perf_counter()
    graph = await _get_async_graph()
    config = {"configurable": {"thread_id": request.session_id, "checkpoint_ns": "agentic_chat"}}
    final_state = await graph.ainvoke(_initial_state(request), config)
    plan = final_state.get("supervisor_plan") or {}
    return AgentChatResponse(
        request_id=request.request_id,
        final_response=final_state.get("final_response", ""),
        agents_used=final_state.get("agents_used", []),
        sources=final_state.get("final_sources", []),
        suggested_actions=final_state.get("suggested_actions", []),
        trace_summary=TraceSummary(
            intent=plan.get("intent", "unknown"),
            agents=final_state.get("agents_used", []),
            source_count=len(final_state.get("final_sources", [])),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        ),
        full_trace={"graph_version": settings.AGENT_GRAPH_VERSION, "mode": "supervisor_specialist_fc"},
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
    graph = await _get_async_graph()
    config = {"configurable": {"thread_id": request.session_id, "checkpoint_ns": "agentic_chat"}}
    initial = _initial_state(request)

    NODE_STATUS: dict[str, str] = {
        "supervisor": "đang phân tích câu hỏi...",
        "specialist": "đang tìm kiếm và phân tích dữ liệu...",
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
