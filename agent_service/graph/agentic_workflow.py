"""
LangGraph-based Agentic RAG workflow.

Replaces the pure-Python OrchestratorAgent with a LangGraph StateGraph
that provides: checkpointing (SQLite), streaming, and built-in retry.

Graph structure:
    supervisor (plan + select agents)
      → specialist (parallel via Send)
      → synthesize (grounded merge + cards)

State is tracked in GraphState; non-streaming responses come from ainvoke.
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
    AgentSource,
    TraceSummary,
    ToolDef,
)
from agent_service.graph.router import route_request
from agent_service.graph.synthesis import synthesize_final_answer
from agent_service.llm.gemini import GeminiClient
from agent_service.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ── LangGraph State ───────────────────────────────────────────────

def _merge_dicts(a: dict, b: dict) -> dict:
    """Reducer for parallel Send writes; empty new dict resets (for retry)."""
    if b == {}:
        return {}
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
    final_charts: list
    correction_round: int


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
        "final_charts": [],
        "correction_round": 0,
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
        name="search_web",
        description=(
            "Tìm kiếm web (Tavily) để bổ sung thông tin pháp lý/tin tức từ "
            "internet. Dùng khi search_articles không trả về kết quả nào, HOẶC "
            "khi kết quả trả về không liên quan / không đủ để trả lời câu hỏi."
        ),
        parameters={"query": "str", "max_results": "int"},
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
    async def _search_web_wrapper(*, query, max_results=5):
        from agent_service.tools.web import search_web
        return await search_web(query, max_results=max_results)

    @with_retry
    async def _market_metrics_wrapper(*, filters):
        results = await lookup_market_metrics(filters=filters or {})
        # Each metric record carries a stable `source_identity`; expose it as
        # evidence so grounded synthesis can cite market figures instead of
        # falling back to deterministic concatenation.
        evidence_ids = [
            r["source_identity"]
            for r in results
            if isinstance(r, dict) and r.get("source_identity")
        ]
        return {"status": "success", "results": results, "evidence_ids": evidence_ids}

    @with_retry
    async def _market_timeseries_wrapper(*, filters):
        results = await lookup_market_timeseries(filters=filters or {})
        evidence_ids = [
            f"market_ts:{r.get('district') or r.get('city') or 'all'}:"
            f"{r.get('property_type') or 'all'}:{r.get('snapshot_month')}"
            for r in results
            if isinstance(r, dict) and r.get("snapshot_month")
        ]
        return {"status": "success", "results": results, "evidence_ids": evidence_ids}

    registry.bind("search_listings", _search_listings_wrapper)
    registry.bind("search_projects", _search_projects_wrapper)
    registry.bind("search_articles", _search_articles_wrapper)
    registry.bind("search_web", _search_web_wrapper)
    registry.bind("lookup_market_metrics", _market_metrics_wrapper)
    registry.bind("lookup_market_timeseries", _market_timeseries_wrapper)

    return registry


_registry: ToolRegistry | None = None


def get_agentic_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = build_default_tool_registry()
    return _registry


# ── LLM client + supervisor/specialist/synthesize nodes ───────────

_DEFAULT_ACTIONS = ["Tìm bất động sản", "Phân tích thị trường", "Tư vấn pháp lý"]


async def _answer_off_topic(query: str, llm_client) -> dict[str, Any] | None:
    """Best-effort: answer an off-topic query from web results, then steer back.

    Returns a synthesize payload, or None to fall back to the polite refusal
    (no Tavily key, no results, no LLM, or any failure).
    """
    if llm_client is None:
        return None
    from agent_service.tools.web import search_web
    try:
        web = await search_web(query, max_results=3)
    except Exception as exc:
        logger.warning("off-topic web search failed: %s", exc)
        return None
    results = web.get("results") or []
    if not results:
        return None

    snippets = "\n".join(
        f"- {r.get('title')}: {r.get('snippet')} (nguồn: {r.get('url')})"
        for r in results
    )
    text = await llm_client.generate_text(
        "Trả lời NGẮN GỌN (tối đa 3 câu, tiếng Việt) câu hỏi sau, chỉ dựa trên "
        "các kết quả web bên dưới, nhắc tên nguồn khi phù hợp. Không bịa.\n"
        f"Câu hỏi: {query}\n"
        f"Kết quả web:\n{snippets}"
    )
    if not (text or "").strip():
        return None

    steer = (
        "\n\n💡 Tôi là trợ lý tư vấn bất động sản — nếu bạn cần tìm nhà, "
        "xem giá thị trường hay hỏi pháp lý, cứ nhắn tôi nhé!"
    )
    sources = [
        AgentSource(type="web", title=r.get("title"), url=r.get("url"))
        for r in results
    ]
    return {
        "final_response": text.strip() + steer,
        "final_sources": sources,
        "suggested_actions": _DEFAULT_ACTIONS,
    }


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
    plan = state.get("supervisor_plan") or {}
    rewritten_query = plan.get("rewritten_query") or request.message
    context = AgentContext(
        agent_name=agent_name,
        query=rewritten_query,
        normalized_query=rewritten_query.lower(),
        routing_filters=state.get("routing_filters", {}),
        conversation_context=state.get("conversation_context", []),
        user_preferences=request.user_preferences,
        locale=request.locale,
        query_understanding={"rewritten_query": rewritten_query, "original_query": request.message},
    )
    result = await run_specialist(
        agent_name=agent_name, context=context, registry=registry,
        llm_client=_make_llm_client(settings), settings=settings,
    )
    rd = result.model_dump(mode="python")
    evidence = {eid: {"agent": agent_name} for eid in result.evidence_ids_used}
    return {"_agent_results": {agent_name: rd}, "evidence_by_id": evidence}


def _collect_charts(raw_results: dict[str, Any], agents_used: list[str]) -> list[dict]:
    """Gather chart specs emitted by the agents that actually ran."""
    charts: list[dict] = []
    for name in agents_used:
        agent_charts = (raw_results.get(name) or {}).get("charts")
        if not isinstance(agent_charts, list):
            continue
        for chart in agent_charts:
            if isinstance(chart, dict):
                charts.append(chart)
    return charts


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
        if plan.get("intent") == "off_topic":
            # Try a web-grounded answer first, then steer back to real estate;
            # degrade to the polite refusal when web search isn't available.
            answered = await _answer_off_topic(
                state["request"].message, _make_llm_client(settings)
            )
            if answered:
                return answered
            return {"final_response": "Xin lỗi, tôi là trợ lý tư vấn bất động sản nên chưa hỗ trợ "
                    "chủ đề này. Tôi có thể giúp bạn tìm nhà/căn hộ, phân tích giá thị trường, "
                    "tư vấn pháp lý hoặc đầu tư bất động sản — bạn quan tâm điều gì?",
                    "final_sources": [], "suggested_actions": _DEFAULT_ACTIONS}
        return {"final_response": "Xin chào! Tôi có thể giúp bạn tìm bất động sản, phân tích thị "
                "trường, hoặc tư vấn pháp lý. Bạn muốn tìm hiểu vấn đề gì?",
                "final_sources": [], "suggested_actions": _DEFAULT_ACTIONS}

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

    logger.info(
        "synthesize used_llm=%s warnings=%s agents=%s allowed_evidence=%d final_len=%d",
        synth.used_llm, synth.warnings, agents_used,
        len(allowed_evidence_ids), len(synth.final_response or ""),
    )

    final = synth.final_response
    if "legal_advisor" in agents_used and "không thay thế tư vấn luật sư" not in final.lower():
        final += "\n\n> ⚠️ Thông tin pháp lý chỉ mang tính tham khảo, không thay thế tư vấn luật sư."
    if "investment_advisor" in agents_used and "không phải lời khuyên tài chính" not in final.lower():
        final += "\n\n> ⚠️ Đây không phải lời khuyên tài chính."

    deduped = list({(s.type, s.id or s.url or s.title): s for s in all_sources}.values())
    return {"final_response": final, "final_sources": deduped,
            "suggested_actions": synth.suggested_actions[:5],
            "final_charts": _collect_charts(raw_results, agents_used)}


# ── Self-correction (grade → rewrite) ─────────────────────────────

_RELAXABLE_KEYS = ("bedrooms", "price_max", "max_price", "district", "area_max", "max_area")


def _relaxable_filters(filters: dict[str, Any]) -> bool:
    """True nếu filter có ràng buộc có thể nới để cứu 0-kết-quả."""
    return any(filters.get(k) not in (None, "") for k in _RELAXABLE_KEYS)


def _relax_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """Nới filter: bỏ bedrooms/district phụ, +20% price bound, +20% area bound."""
    relaxed = dict(filters)
    relaxed.pop("bedrooms", None)
    relaxed.pop("num_bedrooms", None)
    relaxed.pop("district", None)
    for pk in ("price_max", "max_price"):
        if isinstance(relaxed.get(pk), (int, float)):
            relaxed[pk] = round(relaxed[pk] * 1.2, 4)
    for ak in ("area_max", "max_area"):
        if isinstance(relaxed.get(ak), (int, float)):
            relaxed[ak] = round(relaxed[ak] * 1.2, 4)
    return relaxed


def _best_rerank_score(results: dict[str, Any]) -> float | None:
    """Điểm rerank cao nhất trên mọi source của mọi agent.

    Điểm nằm ở AgentSource.score (do specialist copy từ matched_chunk.rerank_score)."""
    scores = [
        s["score"]
        for rd in results.values()
        for s in rd.get("sources", [])
        if isinstance(s, dict) and isinstance(s.get("score"), (int, float))
    ]
    return max(scores) if scores else None


def _grade_decision(state: dict[str, Any]) -> str:
    """Heuristic grade (0 LLM): 'rewrite' để tự sửa, 'synthesize' để trả lời."""
    settings = get_agent_settings()
    if state.get("correction_round", 0) >= settings.AGENT_MAX_CORRECTION_ROUNDS:
        return "synthesize"

    results = state.get("_agent_results", {})
    filters = state.get("routing_filters", {}) or {}

    has_evidence = any(
        rd.get("status") not in ("no_evidence", "failed") and rd.get("sources")
        for rd in results.values()
    )
    if not has_evidence:
        # 0 kết quả: chỉ retry nếu filter nới được, nếu không → trả lời trung thực
        return "rewrite" if _relaxable_filters(filters) else "synthesize"

    best = _best_rerank_score(results)
    if best is not None and best < settings.AGENT_GRADE_MIN_SCORE and _relaxable_filters(filters):
        return "rewrite"
    return "synthesize"


async def _node_grade(state: dict[str, Any]) -> dict[str, Any]:
    """No-op node: quyết định thực nằm ở conditional edge _grade_decision."""
    return {}


async def _node_rewrite(state: dict[str, Any]) -> dict[str, Any]:
    """Nới filter (deterministic) + paraphrase truy vấn (1 LLM call), tăng round."""
    filters = state.get("routing_filters", {}) or {}
    plan = dict(state.get("supervisor_plan") or {})

    new_filters = _relax_filters(filters)

    # LLM paraphrase (best-effort; giữ query cũ nếu lỗi/không có client)
    settings = get_agent_settings()
    llm_client = _make_llm_client(settings)
    original = plan.get("rewritten_query") or state["request"].message
    if llm_client is not None:
        try:
            data = await llm_client.generate_json(
                "Viết lại truy vấn bất động sản sau ngắn gọn, giữ nguyên ý, "
                "nới lỏng ràng buộc quá chặt. Trả JSON {\"query\": \"...\"}.\n"
                f"Truy vấn: {original}",
                timeout_seconds=settings.AGENT_LLM_QUERY_TIMEOUT_SECONDS,
            )
            if isinstance(data, dict) and data.get("query"):
                plan["rewritten_query"] = str(data["query"])
        except Exception as exc:  # paraphrase là best-effort
            logger.warning("rewrite paraphrase failed: %s", exc)

    # Reset kết quả cũ để specialist chạy lại sạch (merge reducer thay thế key).
    return {
        "routing_filters": new_filters,
        "supervisor_plan": plan,
        "correction_round": state.get("correction_round", 0) + 1,
        "_agent_results": {},
        "evidence_by_id": {},
    }


# ── Graph Builder ─────────────────────────────────────────────────

def _new_state_graph() -> StateGraph:
    """Build the supervisor → specialist → grade → (rewrite|synthesize) StateGraph."""
    graph = StateGraph(GraphState)
    graph.add_node("supervisor", _node_supervisor)
    graph.add_node("specialist", _node_specialist)
    graph.add_node("grade", _node_grade)
    graph.add_node("rewrite", _node_rewrite)
    graph.add_node("synthesize", _node_synthesize)
    graph.set_entry_point("supervisor")
    graph.add_conditional_edges("supervisor", _dispatch, ["specialist", "synthesize"])
    graph.add_edge("specialist", "grade")
    graph.add_conditional_edges("grade", _grade_decision, ["synthesize", "rewrite"])
    # rewrite must re-emit Send fan-out (specialist needs per-agent agent_name),
    # so route through _dispatch rather than a plain edge.
    graph.add_conditional_edges("rewrite", _dispatch, ["specialist", "synthesize"])
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
        charts=final_state.get("final_charts", []),
        trace_summary=TraceSummary(
            intent=plan.get("intent", "unknown"),
            agents=final_state.get("agents_used", []),
            source_count=len(final_state.get("final_sources", [])),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        ),
        full_trace={
            "graph_version": settings.AGENT_GRAPH_VERSION,
            "mode": "supervisor_specialist_fc",
            "correction_round": final_state.get("correction_round", 0),
        },
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
        "grade": "đang đánh giá kết quả...",
        "rewrite": "đang tinh chỉnh truy vấn...",
        "synthesize": "đang tổng hợp kết quả...",
    }
    node_started: dict[str, float] = {}
    # Accumulate node outputs as they stream. The graph compiles without a
    # checkpointer by default, so we must read the final answer from the stream
    # itself — `aget_state` would raise "No checkpointer set". On a self-correction
    # retry `_agent_results` accumulates stale+new here (plain merge, not the
    # reset-aware graph reducer), but that key is never read from `vs`: the terminal
    # keys (final_response/final_sources/suggested_actions, agents_used) are written
    # once by synthesize, so reading them from a plain merge is correct.
    vs: dict[str, Any] = {}

    try:
        async for event in graph.astream(initial, config, stream_mode="updates"):
            for node_name, node_output in event.items():
                now = time.perf_counter()
                vs.update(node_output or {})
                if node_name not in node_started:
                    node_started[node_name] = now
                    yield {"event": "node_start", "node": node_name, "status": NODE_STATUS.get(node_name, f"xử lý {node_name}..."), "payload": {}}
                yield {"event": "node_complete", "node": node_name,
                    "duration_ms": round((now - node_started.get(node_name, now)) * 1000, 2),
                    "payload": {k: v for k, v in (node_output or {}).items() if k in ("agents_used", "suggested_actions")}}

        response = AgentChatResponse(
            request_id=request.request_id,
            final_response=vs.get("final_response", ""),
            agents_used=vs.get("agents_used", []),
            sources=vs.get("final_sources", []),
            suggested_actions=vs.get("suggested_actions", []),
            charts=vs.get("final_charts", []),
            trace_summary=TraceSummary(
                # Real router intent (supervisor wrote supervisor_plan into vs),
                # not the "streaming" placeholder — keeps intent stats correct.
                intent=(vs.get("supervisor_plan") or {}).get("intent", "unknown"),
                agents=vs.get("agents_used", []),
                source_count=len(vs.get("final_sources", [])),
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            ),
            full_trace={
                "graph_version": settings.AGENT_GRAPH_VERSION,
                "streaming": True,
                "correction_round": vs.get("correction_round", 0),
            },
        )
        yield {"event": "final", "request_id": request.request_id, "payload": response.model_dump(mode="json")}

    except Exception as exc:
        logger.exception("Agentic stream failed")
        yield {"event": "error", "request_id": request.request_id, "payload": {"code": "graph_stream_error", "message": str(exc)}}
