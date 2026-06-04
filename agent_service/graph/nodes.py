from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

from agent_service.agents.specialists import (
    run_investment_agent,
    run_legal_agent,
    run_market_agent,
    run_news_agent,
    run_project_agent,
    run_property_agent,
)
from agent_service.contracts import AgentSource, MemoryProposal
from agent_service.graph.state import AgentGraphState
from agent_service.tools.readiness import build_readiness_snapshot


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


def _strip_accents(value: str | None) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    without_marks = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return without_marks.lower()


def _normalized_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value))


def _keyword_matches(
    keyword: str,
    normalized_query: str,
    normalized_tokens: set[str],
) -> bool:
    normalized_keyword = _strip_accents(keyword)
    stripped_keyword = normalized_keyword.strip()
    if not stripped_keyword:
        return False
    if stripped_keyword != normalized_keyword or " " in stripped_keyword:
        return normalized_keyword in normalized_query
    return stripped_keyword in normalized_tokens


def _trace_step(name: str, started: float, output: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_name": name,
        "status": "success",
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "output": output,
    }


def _append_trace(
    state: AgentGraphState,
    step_name: str,
    start_time: float,
    output: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    trace_steps = list(state.get("trace_steps", []))
    trace_steps.append(_trace_step(step_name, start_time, output or {}))
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


async def readiness_checker(state: AgentGraphState) -> AgentGraphState:
    started = time.perf_counter()
    readiness = await build_readiness_snapshot()
    steps = state.get("trace_steps", [])
    steps.append(_trace_step("readiness_checker", started, readiness))
    return {**state, "readiness": readiness, "trace_steps": steps}


def router_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    normalized_query = state.get("normalized_query", "")
    normalized_tokens = _normalized_tokens(normalized_query)
    agents_to_run = [
        agent
        for agent in AGENT_ORDER
        if any(
            _keyword_matches(keyword, normalized_query, normalized_tokens)
            for keyword in KEYWORDS_BY_AGENT[agent]
        )
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


async def specialist_agents_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    request = state["request"]
    evidence = state.get("evidence", {})
    runners = {
        "property_search": run_property_agent,
        "project_agent": run_project_agent,
        "market_analysis": run_market_agent,
        "news_agent": run_news_agent,
        "legal_advisor": run_legal_agent,
        "investment_advisor": run_investment_agent,
    }
    agent_results = {}
    for agent in state.get("agents_to_run", []):
        runner = runners.get(agent)
        if runner is None:
            continue
        agent_results[agent] = await runner(
            query=request.message,
            evidence=evidence.get(agent, []),
            preferences=request.user_preferences,
            readiness=state.get("readiness", {}),
        )

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
    parts: list[str] = []
    sources: list[AgentSource] = []
    warnings = list(state.get("warnings", []))

    for agent in state.get("agents_to_run", []):
        result = agent_results.get(agent)
        if not result:
            continue
        content = result.get("content", "")
        if content:
            parts.append(content)
        warnings.extend(result.get("warnings", []))
        for source in result.get("sources", []):
            if isinstance(source, AgentSource):
                sources.append(source)
            else:
                sources.append(AgentSource.model_validate(source))

    final_response = "\n\n".join(parts) or "Chua co du thong tin de tra loi yeu cau nay."
    suggested_actions = ["So sanh lua chon", "Hoi them ve phap ly", "Xem xu huong khu vuc"]
    return {
        "final_response": final_response,
        "sources": sources,
        "suggested_actions": suggested_actions,
        "warnings": warnings,
        "trace_steps": _append_trace(
            state,
            "synthesizer",
            start_time,
            {"answer_length": len(final_response), "source_count": len(sources)},
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
