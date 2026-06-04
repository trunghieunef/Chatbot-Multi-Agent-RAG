from __future__ import annotations

import time
import unicodedata
from typing import Any

from agent_service.contracts import MemoryProposal
from agent_service.graph.state import AgentGraphState


AGENT_ORDER = [
    "legal_advisor",
    "investment_advisor",
    "market_analysis",
    "news_agent",
    "project_agent",
    "property_search",
]

INTENT_BY_AGENT = {
    "legal_advisor": "legal_advice",
    "investment_advisor": "investment_advice",
    "market_analysis": "market_analysis",
    "news_agent": "news",
    "project_agent": "project",
    "property_search": "property_search",
}

KEYWORDS_BY_AGENT = {
    "legal_advisor": ["phap ly", "luat", "thu tuc", "cong chung", "so do", "sang ten"],
    "investment_advisor": ["dau tu", "roi", "loi nhuan", "sinh loi", "rental yield"],
    "market_analysis": ["thi truong", "xu huong", "thong ke", "gia trung binh"],
    "news_agent": ["tin tuc", "bao chi", "cap nhat"],
    "project_agent": ["du an", "chu dau tu"],
    "property_search": ["tim", "mua", "thue", "can ho", "nha", "dat", "quan "],
}


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    without_marks = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return without_marks.lower()


def _trace_step(
    step_name: str,
    status: str = "ok",
    latency_ms: float = 0.0,
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "step_name": step_name,
        "status": status,
        "latency_ms": latency_ms,
        "output": output or {},
    }


def _append_trace(
    state: AgentGraphState,
    step_name: str,
    start_time: float,
    output: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    trace_steps = list(state.get("trace_steps", []))
    trace_steps.append(
        _trace_step(
            step_name=step_name,
            latency_ms=(time.perf_counter() - start_time) * 1000,
            output=output,
        )
    )
    return trace_steps


def context_builder(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    request = state["request"]
    normalized_query = _strip_accents(request.message)
    return {
        "normalized_query": normalized_query,
        "trace_steps": _append_trace(
            state,
            "context_builder",
            start_time,
            {"context_items": len(request.conversation_context)},
        ),
    }


def readiness_checker(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    readiness = {
        "listings": "unknown",
        "projects": "unknown",
        "news": "unknown",
        "legal": "unknown",
        "chunks": "unknown",
    }
    return {
        "readiness": readiness,
        "trace_steps": _append_trace(
            state,
            "readiness_checker",
            start_time,
            {"sources": readiness},
        ),
    }


def router_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    normalized_query = state.get("normalized_query", "")
    agents_to_run = [
        agent
        for agent in AGENT_ORDER
        if any(keyword in normalized_query for keyword in KEYWORDS_BY_AGENT[agent])
    ]

    if not agents_to_run:
        agents_to_run = ["property_search"]

    intent = (
        INTENT_BY_AGENT[agents_to_run[0]]
        if len(agents_to_run) == 1
        else "mixed"
    )
    routing_filters = {
        "locale": state["request"].locale,
        "user_preferences": state["request"].user_preferences,
    }
    return {
        "intent": intent,
        "agents_to_run": agents_to_run,
        "routing_filters": routing_filters,
        "trace_steps": _append_trace(
            state,
            "router",
            start_time,
            {"intent": intent, "agents_to_run": agents_to_run},
        ),
    }


def retrieval_planner_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    evidence = {agent: [] for agent in state.get("agents_to_run", [])}
    return {
        "evidence": evidence,
        "sources": [],
        "trace_steps": _append_trace(
            state,
            "retrieval_planner",
            start_time,
            {"planned_agents": list(evidence)},
        ),
    }


def specialist_agents_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    request = state["request"]
    agent_results = {
        agent: (
            f"{agent} processed request {request.request_id} offline "
            f"for query: {request.message}"
        )
        for agent in state.get("agents_to_run", [])
    }
    return {
        "agent_results": agent_results,
        "trace_steps": _append_trace(
            state,
            "specialist_agents",
            start_time,
            {"agents_completed": list(agent_results)},
        ),
    }


def synthesizer_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    agent_results = state.get("agent_results", {})
    content = " ".join(agent_results[agent] for agent in state.get("agents_to_run", []))
    final_response = content or "No specialist agents produced a response."
    suggested_actions = ["review_sources", "refine_search"]
    return {
        "final_response": final_response,
        "suggested_actions": suggested_actions,
        "trace_steps": _append_trace(
            state,
            "synthesizer",
            start_time,
            {"suggested_actions": suggested_actions},
        ),
    }


def memory_proposal_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    memory_proposals: list[MemoryProposal] = []
    if "quan 7" in state.get("normalized_query", ""):
        memory_proposals.append(
            MemoryProposal(
                action="upsert",
                key="preferred_district",
                value="Quan 7",
                confidence=0.8,
                evidence="User mentioned Quan 7 in the current query.",
            )
        )

    return {
        "memory_proposals": memory_proposals,
        "trace_steps": _append_trace(
            state,
            "memory_proposals",
            start_time,
            {"proposal_count": len(memory_proposals)},
        ),
    }
