from __future__ import annotations

import asyncio
import time

import pytest

from agent_service.contracts import AgentChatRequest, RetrievalTask
from agent_service.graph import retrieval_planner
from agent_service.graph.retrieval_planner import execute_retrieval_plan


def _state() -> dict:
    return {
        "request": AgentChatRequest(
            request_id="req-parallel-retrieval",
            session_id="session-1",
            message="Tim can ho Quan 7 va thong tin phap ly",
        ),
        "agents_to_run": ["property_search", "legal_advisor"],
        "warnings": [],
    }


@pytest.mark.asyncio
async def test_execute_retrieval_plan_runs_independent_tasks_concurrently(monkeypatch):
    started: list[str] = []

    async def fake_run_hybrid_tool(**kwargs):
        started.append(kwargs["parent_type"])
        await asyncio.sleep(0.1)
        return [
            {
                "id": kwargs["parent_type"],
                "title": f"{kwargs['parent_type']} result",
                "url": f"https://example.test/{kwargs['parent_type']}",
                "matched_chunk": {
                    "id": f"chunk-{kwargs['parent_type']}",
                    "text": "matched text",
                    "rerank_score": 0.9,
                },
            }
        ]

    monkeypatch.setattr(retrieval_planner, "_run_hybrid_tool", fake_run_hybrid_tool)
    plan = [
        RetrievalTask(
            task_id="search_property_1",
            domain="property",
            tool="search_listings",
            query="can ho quan 7",
            filters={},
            retrieved_for=["property_search"],
        ),
        RetrievalTask(
            task_id="search_legal_1",
            domain="legal",
            tool="search_articles",
            query="phap ly can ho",
            filters={"category": "legal"},
            retrieved_for=["legal_advisor"],
        ),
    ]

    started_at = time.perf_counter()
    update = await execute_retrieval_plan(plan, _state())
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.18
    assert set(started) == {"listing", "article"}
    assert update["retrieval_results"]["search_property_1"].status == "completed"
    assert update["retrieval_results"]["search_legal_1"].status == "completed"
