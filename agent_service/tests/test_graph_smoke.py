from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph import nodes
from agent_service.graph.workflow import run_agent_graph


@pytest.mark.asyncio
async def test_agent_graph_smoke_without_ready_sources(monkeypatch):
    async def fake_readiness_snapshot():
        return {
            "listings": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "projects": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "news": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "legal": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
        }

    monkeypatch.setattr(nodes, "build_readiness_snapshot", fake_readiness_snapshot)

    response = await run_agent_graph(
        AgentChatRequest(
            request_id="req-agent-service-smoke",
            session_id="session-1",
            message="Tim can ho Quan 7",
        )
    )

    assert response.request_id == "req-agent-service-smoke"
    assert response.final_response
    assert response.full_trace["steps"]
