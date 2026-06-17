from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph import nodes
from agent_service.graph import retrieval_planner
from agent_service.graph.workflow import run_agent_graph


@pytest.mark.asyncio
async def test_collaborative_investment_graph_returns_scorecard_and_trace(monkeypatch):
    async def fake_readiness_snapshot():
        return {
            "listings": {"status": "ready", "parent_count": 1, "chunk_count": 1},
            "projects": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "news": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "legal": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
        }

    async def fake_run_hybrid_tool(**kwargs):
        if kwargs["parent_type"] == "listing":
            return [
                {
                    "id": 1,
                    "product_id": "p1",
                    "title": "Can ho Quan 7",
                    "price": 4.8,
                    "area": 75,
                    "price_text": "4.8 ty",
                    "area_text": "75 m2",
                    "url": "https://example.test/p1",
                    "matched_chunk": {
                        "id": "chunk1",
                        "text": "Can ho Quan 7 gia 4.8 ty dien tich 75 m2",
                        "rerank_score": 0.9,
                    },
                }
            ]
        return []

    monkeypatch.setattr(nodes, "build_readiness_snapshot", fake_readiness_snapshot)
    monkeypatch.setattr(retrieval_planner, "_run_hybrid_tool", fake_run_hybrid_tool)

    response = await run_agent_graph(
        AgentChatRequest(
            request_id="req-collab-invest",
            session_id="s1",
            message="Co nen dau tu can ho Quan 7 nay khong?",
        )
    )

    assert "Scorecard dau tu" in response.final_response
    assert "khong phai loi khuyen tai chinh" in response.final_response
    assert response.full_trace["investment_case"]
    assert response.full_trace["investment_metrics"]
    assert response.full_trace["committee_review"]["perspectives"]
