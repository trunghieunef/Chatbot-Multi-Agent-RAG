import pytest

from agent_service.tools.retrieval import (
    RetrievalTrace,
    _run_hybrid_tool,
    search_articles,
    search_listings,
)
from agent_service.tools.readiness import build_readiness_snapshot, count_source


def test_retrieval_trace_add_event_defaults_status_to_success():
    trace = RetrievalTrace(request_id="req-1")

    trace.add_event(
        tool_name="search_listings",
        parent_type="listing",
        filters=None,
        result_count=0,
        latency_ms=1.2,
    )

    assert trace.events[0]["status"] == "success"


@pytest.mark.asyncio
async def test_search_listings_records_trace(monkeypatch):
    async def fake_hybrid_search(query, filters=None, parent_type="listing", top_k=20, rerank_to=5):
        assert parent_type == "listing"
        return [{"id": 1, "title": "Can ho Quan 7", "matched_chunk": {"distance": 0.2}}]

    monkeypatch.setattr("agent_service.tools.retrieval.hybrid_search", fake_hybrid_search)
    trace = RetrievalTrace(request_id="req-1")

    results = await search_listings("Tim nha", {"district": "Quan 7"}, trace)

    assert results[0]["title"] == "Can ho Quan 7"
    assert trace.events[0]["tool_name"] == "search_listings"
    assert trace.events[0]["result_count"] == 1


@pytest.mark.asyncio
async def test_search_articles_uses_parent_type_article(monkeypatch):
    called = {}

    async def fake_hybrid_search(query, filters=None, parent_type="listing", top_k=20, rerank_to=5):
        called["parent_type"] = parent_type
        called["filters"] = filters
        return [{"id": 7, "title": "Tin thi truong"}]

    monkeypatch.setattr("agent_service.tools.retrieval.hybrid_search", fake_hybrid_search)
    trace = RetrievalTrace(request_id="req-1")

    await search_articles("tin thi truong", {"category": "news"}, trace)

    assert called == {"parent_type": "article", "filters": {"category": "news"}}


@pytest.mark.asyncio
async def test_run_hybrid_tool_passes_custom_limits(monkeypatch):
    called = {}

    async def fake_hybrid_search(query, filters=None, parent_type="listing", top_k=20, rerank_to=5):
        called["top_k"] = top_k
        called["rerank_to"] = rerank_to
        return []

    monkeypatch.setattr("agent_service.tools.retrieval.hybrid_search", fake_hybrid_search)
    trace = RetrievalTrace(request_id="req-1")

    await _run_hybrid_tool(
        query="tim nha",
        filters=None,
        trace=trace,
        tool_name="search_listings",
        parent_type="listing",
        top_k=7,
        rerank_to=3,
    )

    assert called == {"top_k": 7, "rerank_to": 3}


@pytest.mark.asyncio
async def test_count_source_returns_not_ready_for_unsupported_source():
    result = await count_source("unsupported")

    assert result == {
        "status": "not_ready",
        "parent_count": 0,
        "chunk_count": 0,
    }


@pytest.mark.asyncio
async def test_build_readiness_snapshot_returns_default_when_db_unavailable(monkeypatch):
    async def exploding_count_source(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr("agent_service.tools.readiness.count_source", exploding_count_source)

    snapshot = await build_readiness_snapshot()

    assert snapshot["listings"]["status"] == "unknown"
    assert snapshot["legal"]["status"] == "unknown"
