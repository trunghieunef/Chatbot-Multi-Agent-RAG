from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph import agentic_workflow as wf
from agent_service.graph.router import RouterDecision


@pytest.mark.asyncio
async def test_degrades_to_retrieval_without_llm(monkeypatch):
    async def fake_route(state, client=None):
        return RouterDecision(
            intent="property_search",
            agents=["property_search"],
            confidence=1.0,
            filters={"city": "HCM"},
        )

    async def fake_hybrid(*, query, filters, parent_type, top_k, rerank_to):
        return [
            {
                "id": 7,
                "title": "Căn E",
                "price_text": "2 tỷ",
                "area_text": "55 m²",
                "district": "Quận 3",
                "city": "HCM",
            }
        ]

    monkeypatch.setattr(wf, "route_request", fake_route)
    monkeypatch.setattr("app.services.rag.hybrid_search.hybrid_search", fake_hybrid)
    monkeypatch.setattr(wf, "_make_llm_client", lambda settings: None)
    monkeypatch.setattr(wf, "_registry", None, raising=False)

    response = await wf.run_agentic_graph(
        AgentChatRequest(
            request_id="e1",
            session_id="s1",
            message="Tìm căn hộ Quận 3",
        )
    )

    assert response.agents_used == ["property_search"]
    assert response.final_response
    assert any(source.id == 7 for source in response.sources)


@pytest.mark.asyncio
async def test_stream_emits_final_without_checkpointer(monkeypatch):
    """Streaming must yield a `final` answer even when no checkpointer is wired.

    Regression: the stream previously read its result via ``aget_state``, which
    raises "No checkpointer set" on the default checkpointer-free graph, so the
    stream emitted an `error` instead of the answer.
    """

    async def fake_route(state, client=None):
        return RouterDecision(
            intent="property_search",
            agents=["property_search"],
            confidence=1.0,
            filters={"city": "HCM"},
        )

    async def fake_hybrid(*, query, filters, parent_type, top_k, rerank_to):
        return [
            {
                "id": 7,
                "title": "Căn E",
                "price_text": "2 tỷ",
                "area_text": "55 m²",
                "district": "Quận 3",
                "city": "HCM",
            }
        ]

    monkeypatch.setattr(wf, "route_request", fake_route)
    monkeypatch.setattr("app.services.rag.hybrid_search.hybrid_search", fake_hybrid)
    monkeypatch.setattr(wf, "_make_llm_client", lambda settings: None)
    monkeypatch.setattr(wf, "_registry", None, raising=False)

    events = [
        event
        async for event in wf.run_agentic_graph_stream(
            AgentChatRequest(request_id="e2", session_id="s2", message="Tìm căn hộ Quận 3")
        )
    ]

    assert not any(e["event"] == "error" for e in events), [e for e in events if e["event"] == "error"]
    finals = [e for e in events if e["event"] == "final"]
    assert len(finals) == 1
    payload = finals[0]["payload"]
    assert payload["agents_used"] == ["property_search"]
    assert payload["final_response"]
    assert any(src["id"] == 7 for src in payload["sources"])
