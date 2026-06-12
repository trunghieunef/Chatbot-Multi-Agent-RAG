import asyncio

import pytest

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentChatRequest
from agent_service.graph.workflow import run_agent_graph


@pytest.mark.asyncio
async def test_total_timeout_falls_back_deterministically(monkeypatch):
    request = AgentChatRequest(
        request_id="req-timeout",
        message="tu van dau tu quan 7",
        session_id="session-1",
    )

    async def slow_ainvoke(state):
        await asyncio.sleep(0.2)
        return state

    monkeypatch.setattr("agent_service.graph.workflow.chat_graph.ainvoke", slow_ainvoke)
    monkeypatch.setenv("AGENT_TOTAL_TIMEOUT_SECONDS", "0.01")
    get_agent_settings.cache_clear()

    response = await run_agent_graph(request)

    assert "agent_total_timeout_exceeded" in response.trace_summary.warnings
    assert response.final_response
    get_agent_settings.cache_clear()
