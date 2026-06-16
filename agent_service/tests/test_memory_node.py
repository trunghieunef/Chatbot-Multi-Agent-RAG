from __future__ import annotations

from agent_service.contracts import AgentChatRequest
from agent_service.graph.nodes import memory_proposal_node


def test_memory_node_uses_query_understanding_filters():
    state = {
        "request": AgentChatRequest(
            request_id="req-memory-node",
            session_id="session-1",
            message="Toi muon mua can ho Quan 7",
        ),
        "query_understanding": {
            "filters": {
                "listing_type": "sale",
                "property_type": "Can ho",
                "district": "Quan 7",
            }
        },
        "trace_steps": [],
    }

    result = memory_proposal_node(state)
    keys = {proposal.key for proposal in result["memory_proposals"]}

    assert {"listing_type", "preferred_property_type", "preferred_district"}.issubset(keys)
