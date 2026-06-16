from __future__ import annotations

import asyncio
import time

import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph import nodes


@pytest.mark.asyncio
async def test_specialist_agents_node_runs_agents_concurrently(monkeypatch):
    async def fake_agent(**kwargs):
        await asyncio.sleep(0.1)
        return {
            "agent_name": "fake",
            "status": "completed",
            "content": "ok",
            "evidence_ids_used": [],
            "warnings": [],
        }

    monkeypatch.setattr(nodes, "run_property_agent", fake_agent)
    monkeypatch.setattr(nodes, "run_legal_agent", fake_agent)

    state = {
        "request": AgentChatRequest(
            request_id="req-specialists-parallel",
            message="Tim can ho va kiem tra phap ly",
            session_id="session-1",
        ),
        "agents_to_run": ["property_search", "legal_advisor"],
        "evidence_by_id": {},
        "evidence_for_agent": {},
        "readiness": {},
        "warnings": [],
        "trace_steps": [],
        "force_deterministic": True,
    }

    started_at = time.perf_counter()
    result = await nodes.specialist_agents_node(state)
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.18
    assert set(result["agent_results"]) == {"property_search", "legal_advisor"}
