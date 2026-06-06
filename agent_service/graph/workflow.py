from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent_service.contracts import AgentChatRequest, AgentChatResponse, TraceSummary
from agent_service.graph.nodes import (
    context_builder,
    memory_proposal_node,
    readiness_checker,
    retrieval_planner_node,
    router_node,
    safety_validator_node,
    specialist_agents_node,
    synthesizer_node,
)
from agent_service.graph.state import AgentGraphState


def build_agent_graph():
    workflow = StateGraph(AgentGraphState)
    workflow.add_node("context_builder", context_builder)
    workflow.add_node("readiness_checker", readiness_checker)
    workflow.add_node("router", router_node)
    workflow.add_node("retrieval_planner", retrieval_planner_node)
    workflow.add_node("specialist_agents", specialist_agents_node)
    workflow.add_node("synthesizer", synthesizer_node)
    workflow.add_node("safety_validator", safety_validator_node)
    workflow.add_node("memory_proposals", memory_proposal_node)

    workflow.set_entry_point("context_builder")
    workflow.add_edge("context_builder", "readiness_checker")
    workflow.add_edge("readiness_checker", "router")
    workflow.add_edge("router", "retrieval_planner")
    workflow.add_edge("retrieval_planner", "specialist_agents")
    workflow.add_edge("specialist_agents", "synthesizer")
    workflow.add_edge("synthesizer", "safety_validator")
    workflow.add_edge("safety_validator", "memory_proposals")
    workflow.add_edge("memory_proposals", END)
    return workflow.compile()


chat_graph = build_agent_graph()


async def run_agent_graph(request: AgentChatRequest) -> AgentChatResponse:
    result = await chat_graph.ainvoke(
        {"request": request, "trace_steps": [], "warnings": []}
    )
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
