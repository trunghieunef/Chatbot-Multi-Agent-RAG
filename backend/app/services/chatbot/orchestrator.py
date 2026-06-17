"""Production multi-agent chatbot orchestrator."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chatbot.agents.investment import run_investment_advisor
from app.services.chatbot.agents.legal import run_legal_advisor
from app.services.chatbot.agents.market import run_market_analysis
from app.services.chatbot.agents.property import run_property_search
from app.services.chatbot.contracts import AgentResult, RoutingDecision
from app.services.chatbot.router import route_query


AgentRunner = Callable[[str, AsyncSession, RoutingDecision], Awaitable[AgentResult]]

AGENT_RUNNERS: dict[str, AgentRunner] = {
    "property_search": run_property_search,
    "market_analysis": run_market_analysis,
    "legal_advisor": run_legal_advisor,
    "investment_advisor": run_investment_advisor,
}

logger = logging.getLogger(__name__)


def _dedupe_actions(results: list[AgentResult]) -> list[str]:
    actions: list[str] = []
    for result in results:
        for action in result.suggested_actions:
            if action not in actions:
                actions.append(action)
    return actions[:5]


def _combine_results(results: list[AgentResult]) -> dict:
    ordered = sorted(results, key=lambda result: result.agent_name)
    content = "\n\n".join(result.content for result in ordered if result.content)
    sources = [source for result in ordered for source in result.sources]
    return {
        "final_response": content or "Tôi chưa tạo được câu trả lời phù hợp.",
        "agent_used": ", ".join(result.agent_name for result in ordered) or "none",
        "sources": sources,
        "suggested_actions": _dedupe_actions(ordered),
    }


async def run_chat_pipeline(
    query: str,
    db: AsyncSession,
    session_id: str | None = None,
) -> dict:
    """Run router, selected specialist agents, and response synthesis."""
    started = time.perf_counter()
    routing = route_query(query)
    selected = [
        AGENT_RUNNERS[agent_name]
        for agent_name in routing.target_agents
        if agent_name in AGENT_RUNNERS
    ]
    if not selected:
        selected = [AGENT_RUNNERS["property_search"]]

    results = await asyncio.gather(
        *(runner(query, db, routing) for runner in selected)
    )
    combined = _combine_results(list(results))
    logger.info(
        "chat_pipeline_completed",
        extra={
            "session_id": session_id,
            "intent": routing.intent,
            "target_agents": routing.target_agents,
            "agent_used": combined["agent_used"],
            "source_count": len(combined.get("sources") or []),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return combined
