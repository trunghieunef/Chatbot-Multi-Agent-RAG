from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest, AgentSource, Evidence
from agent_service.graph import nodes


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="ev_listing",
        retrieval_task_id="search_property_1",
        domain="property",
        source_type="listing",
        source_identity="listing:p1",
        record={},
        facts={"title": "Can ho Quan 7", "price": 4.8, "area": 75},
        source=AgentSource(type="listing", domain="property", id="p1"),
        retrieved_for=["property_search", "investment_advisor"],
        assigned_to=["property_search", "investment_advisor"],
    )


@pytest.mark.asyncio
async def test_specialist_agents_node_writes_blackboard_entries(monkeypatch):
    async def fake_property_agent(**kwargs):
        return {
            "agent_name": "property_search",
            "status": "completed",
            "content": "Listing phu hop de sang loc dau tu.",
            "evidence_ids_used": ["ev_listing"],
            "confidence": "high",
            "warnings": [],
        }

    monkeypatch.setattr(nodes, "run_property_agent", fake_property_agent)
    state = {
        "request": AgentChatRequest(
            request_id="req-bb-specialist",
            session_id="s1",
            message="Co nen dau tu can ho nay?",
        ),
        "agents_to_run": ["property_search"],
        "evidence_by_id": {"ev_listing": _evidence()},
        "evidence_for_agent": {"property_search": ["ev_listing"]},
        "readiness": {},
        "warnings": [],
        "trace_steps": [],
        "force_deterministic": True,
    }

    result = await nodes.specialist_agents_node(state)

    entries = result["agent_blackboard"]["entries"]
    assert entries[0]["author"] == "property_search"
    assert entries[0]["evidence_ids"] == ["ev_listing"]
    assert entries[0]["content"]["status"] == "completed"
