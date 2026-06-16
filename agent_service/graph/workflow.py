from __future__ import annotations

import asyncio

from langgraph.graph import END, StateGraph

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentChatRequest, AgentChatResponse, TraceSummary
from agent_service.graph.nodes import (
    committee_review_node,
    context_builder,
    investment_model_node,
    memory_proposal_node,
    query_understanding_node,
    readiness_checker,
    retrieval_planner_node,
    router_node,
    safety_validator_node,
    specialist_agents_node,
    synthesizer_node,
)
from agent_service.graph.state import AgentGraphState


def _route_after_specialists(state: AgentGraphState) -> str:
    return (
        "investment_model"
        if "investment_advisor" in state.get("agents_to_run", [])
        else "synthesizer"
    )


def build_agent_graph():
    workflow = StateGraph(AgentGraphState)
    workflow.add_node("context_builder", context_builder)
    workflow.add_node("readiness_checker", readiness_checker)
    workflow.add_node("router", router_node)
    workflow.add_node("query_understanding", query_understanding_node)
    workflow.add_node("retrieval_planner", retrieval_planner_node)
    workflow.add_node("specialist_agents", specialist_agents_node)
    workflow.add_node("investment_model", investment_model_node)
    workflow.add_node("committee_review", committee_review_node)
    workflow.add_node("synthesizer", synthesizer_node)
    workflow.add_node("safety_validator", safety_validator_node)
    workflow.add_node("memory_proposals", memory_proposal_node)

    workflow.set_entry_point("context_builder")
    workflow.add_edge("context_builder", "readiness_checker")
    workflow.add_edge("readiness_checker", "router")
    workflow.add_edge("router", "query_understanding")
    workflow.add_edge("query_understanding", "retrieval_planner")
    workflow.add_edge("retrieval_planner", "specialist_agents")
    workflow.add_conditional_edges(
        "specialist_agents",
        _route_after_specialists,
        {
            "investment_model": "investment_model",
            "synthesizer": "synthesizer",
        },
    )
    workflow.add_edge("investment_model", "committee_review")
    workflow.add_edge("committee_review", "synthesizer")
    workflow.add_edge("synthesizer", "safety_validator")
    workflow.add_edge("safety_validator", "memory_proposals")
    workflow.add_edge("memory_proposals", END)
    return workflow.compile()


chat_graph = build_agent_graph()


async def _invoke_graph(
    request: AgentChatRequest,
    *,
    force_deterministic: bool = False,
) -> dict:
    return await chat_graph.ainvoke(
        {
            "request": request,
            "trace_steps": [],
            "warnings": [],
            "force_deterministic": force_deterministic,
        }
    )


def _timeout_fallback_result(request: AgentChatRequest) -> dict:
    return {
        "request": request,
        "intent": "fallback",
        "agents_to_run": ["property_search"],
        "final_response": "He thong dang ban, vui long thu lai sau.",
        "sources": [],
        "suggested_actions": ["Thu lai sau"],
        "trace_steps": [],
        "warnings": [
            "agent_total_timeout_exceeded",
            "agent_deterministic_fallback_timeout",
        ],
        "memory_proposals": [],
        "readiness": {},
    }


def _response_from_result(
    request: AgentChatRequest,
    result: dict,
) -> AgentChatResponse:
    settings = get_agent_settings()
    steps = result.get("trace_steps", [])
    agents_used = result.get("agents_to_run", [])
    sources = result.get("sources", [])
    warnings = result.get("warnings", [])
    latency_ms = sum(step.get("latency_ms", 0.0) for step in steps)
    final_response = result.get("final_response", "")

    trace_summary = TraceSummary(
        intent=result.get("intent", "unknown"),
        agents=agents_used,
        source_count=len(sources),
        latency_ms=latency_ms,
        warnings=warnings,
    )
    return AgentChatResponse(
        request_id=request.request_id,
        final_response=final_response,
        agents_used=agents_used,
        sources=sources,
        suggested_actions=result.get("suggested_actions", []),
        trace_summary=trace_summary,
        full_trace={
            "request_id": request.request_id,
            "intelligence": {
                "router_mode": settings.AGENT_ROUTER_MODE,
                "query_rewrite_enabled": settings.AGENT_QUERY_REWRITE_ENABLED,
                "memory_filters_enabled": settings.AGENT_MEMORY_FILTERS_ENABLED,
                "specialist_llm_enabled": settings.AGENT_SPECIALIST_LLM_ENABLED,
                "model_name": settings.GEMINI_MODEL,
                "prompt_version": settings.AGENT_PROMPT_VERSION,
            },
            "steps": steps,
            "agent_results": result.get("agent_results", {}),
            "retrieval_plan": [
                task.model_dump(mode="json") if hasattr(task, "model_dump") else task
                for task in result.get("retrieval_plan", [])
            ],
            "retrieval_results": {
                key: (
                    value.model_dump(mode="json")
                    if hasattr(value, "model_dump")
                    else value
                )
                for key, value in result.get("retrieval_results", {}).items()
            },
            "evidence": {
                key: (
                    value.model_dump(mode="json")
                    if hasattr(value, "model_dump")
                    else value
                )
                for key, value in result.get("evidence_by_id", {}).items()
            },
            "evidence_for_agent": result.get("evidence_for_agent", {}),
            "query_understanding": result.get("query_understanding", {}),
        },
        memory_proposals=result.get("memory_proposals", []),
        readiness=result.get("readiness", {}),
        evaluation_candidate={
            "request_id": request.request_id,
            "answer": final_response,
            "agents_used": agents_used,
            "source_count": len(sources),
        },
    )


async def run_agent_graph(request: AgentChatRequest) -> AgentChatResponse:
    settings = get_agent_settings()
    timeout = settings.AGENT_TOTAL_TIMEOUT_SECONDS
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    try:
        result = await asyncio.wait_for(_invoke_graph(request), timeout=timeout)
    except asyncio.TimeoutError:
        remaining_timeout = max(0.0, deadline - loop.time())
        if remaining_timeout <= 0:
            result = _timeout_fallback_result(request)
        else:
            try:
                result = await asyncio.wait_for(
                    _invoke_graph(request, force_deterministic=True),
                    timeout=remaining_timeout,
                )
                result["warnings"] = [
                    *result.get("warnings", []),
                    "agent_total_timeout_exceeded",
                ]
            except asyncio.TimeoutError:
                result = _timeout_fallback_result(request)

    return _response_from_result(request, result)
