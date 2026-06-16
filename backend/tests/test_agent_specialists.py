import inspect
import sys
import types

import pytest

from agent_service.agents.specialists import (
    _source_from_record,
    run_investment_agent,
    run_legal_agent,
    run_project_agent,
    run_property_agent,
)
from agent_service.contracts import AgentChatRequest, AgentSource, Evidence, MatchedChunk
from agent_service.config import get_agent_settings
from agent_service.graph.nodes import synthesizer_node
from agent_service.llm.gemini import GeminiClient


def _listing_evidence(evidence_id="ev_listing_1"):
    return Evidence(
        evidence_id=evidence_id,
        retrieval_task_id="search_property_1",
        domain="property",
        source_type="listing",
        source_identity="listing:p-1",
        record={},
        facts={
            "title": "Can ho Quan 7",
            "price_text": "4.8 ty",
            "area_text": "75 m2",
            "location": {"district": "Quan 7", "city": "Ho Chi Minh"},
            "legal_status_claimed": "So hong",
        },
        source=AgentSource(type="listing", domain="property", id="listing:p-1"),
        matched_chunks=[
            MatchedChunk(text="Can ho Quan 7 gia 4.8 ty", final_score=0.91)
        ],
        retrieved_for=["property_search"],
        assigned_to=["property_search", "investment_advisor"],
    ).model_dump(mode="python")


def _warning_code(warning):
    if hasattr(warning, "code"):
        return warning.code
    return warning.get("code")


@pytest.mark.asyncio
async def test_gemini_client_generation_methods_are_async_without_api_key():
    assert inspect.iscoroutinefunction(GeminiClient.generate_text)
    assert inspect.iscoroutinefunction(GeminiClient.generate_json)

    client = GeminiClient(api_key="")

    assert await client.generate_text("x") == ""
    assert await client.generate_json("x") == {}


@pytest.mark.asyncio
async def test_gemini_client_uses_worker_thread_when_api_key_is_set(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_COST_TRACKING_ENABLED", "false")
    get_agent_settings.cache_clear()

    class FakeModels:
        def generate_content(self, *, model, contents):
            assert model == "model"
            assert contents == "hello"
            return types.SimpleNamespace(text="threaded response")

    class FakeClient:
        def __init__(self, *, api_key, http_options=None):
            assert api_key == "key"
            assert http_options is not None
            self.models = FakeModels()

    called = False

    async def fake_to_thread(func):
        nonlocal called
        called = True
        return func()

    monkeypatch.setitem(
        sys.modules,
        "google",
        types.SimpleNamespace(genai=types.SimpleNamespace(Client=FakeClient)),
    )
    monkeypatch.setattr("agent_service.llm.gemini.asyncio.to_thread", fake_to_thread)
    client = GeminiClient(api_key="key", model="model")

    assert await client.generate_text("hello") == "threaded response"
    assert called
    get_agent_settings.cache_clear()


def test_source_from_record_uses_rag_fallback_fields():
    source = _source_from_record(
        {
            "id": 123,
            "product_id": "p-123",
            "name": "Fallback listing name",
            "price_range": "4-5 ty",
            "area_range": "60-70 m2",
            "score": 0.12,
            "matched_chunk": {"rerank_score": 0.87},
        },
        "listing",
    )

    assert source["title"] == "Fallback listing name"
    assert source["score"] == 0.87
    assert source["metadata"]["price_text"] == "4-5 ty"
    assert source["metadata"]["area_text"] == "60-70 m2"


@pytest.mark.asyncio
async def test_property_agent_requires_evidence_for_listing_claims():
    result = await run_property_agent(
        query="Tim can ho Quan 7",
        evidence=[
            {
                "id": 1,
                "title": "Can ho Quan 7",
                "district": "Quan 7",
                "city": "Ho Chi Minh",
                "price_text": "4.8 ty",
                "area_text": "70 m2",
                "url": "https://example.test/1",
            }
        ],
        preferences={},
        readiness={"listings": {"status": "ready"}},
    )

    assert result["agent_name"] == "property_search"
    assert "Can ho Quan 7" in result["content"]
    assert result["sources"][0]["type"] == "listing"
    assert result["confidence"] == "high"


@pytest.mark.asyncio
async def test_property_agent_reports_no_evidence_without_fake_listing():
    result = await run_property_agent(
        query="Tim can ho Quan 7",
        evidence=[],
        preferences={},
        readiness={"listings": {"status": "ready"}},
    )

    assert result["status"] == "no_evidence"
    assert result["evidence_ids_used"] == []
    assert "Can ho Quan 7 - 4.8 ty" not in result["content"]


@pytest.mark.asyncio
async def test_property_agent_warns_when_listing_source_not_ready():
    result = await run_property_agent(
        query="Tim can ho Quan 7",
        evidence=[],
        preferences={},
        readiness={"listings": {"status": "not_ready"}},
    )

    assert result["status"] == "no_evidence"
    assert "chua san sang" in result["content"].lower()
    assert _warning_code(result["warnings"][0]) == "listing_source_not_ready"


@pytest.mark.asyncio
async def test_property_agent_uses_evidence_ids_from_assigned_evidence():
    result = await run_property_agent(
        query="Tim can ho Quan 7",
        evidence=[_listing_evidence()],
        preferences={},
        readiness={"listings": {"status": "ready"}},
    )

    assert result["status"] == "completed"
    assert result["evidence_ids_used"] == ["ev_listing_1"]
    assert "Can ho Quan 7" in result["content"]


@pytest.mark.asyncio
async def test_legal_agent_does_not_use_listing_legal_claim_as_legal_proof():
    result = await run_legal_agent(
        query="phap ly on khong",
        evidence=[_listing_evidence()],
        preferences={},
        readiness={"legal": {"status": "ready"}},
    )

    assert result["status"] == "no_evidence"
    assert result["evidence_ids_used"] == []
    assert "du dieu kien phap ly" not in result["content"].lower()


@pytest.mark.asyncio
async def test_investment_agent_warns_when_market_metric_missing():
    result = await run_investment_agent(
        query="dau tu can ho nay",
        evidence=[_listing_evidence()],
        preferences={},
        readiness={"listings": {"status": "ready"}},
    )

    assert result["status"] == "partial"
    assert result["evidence_ids_used"] == ["ev_listing_1"]
    assert any(
        _warning_code(warning) == "investment_market_data_missing"
        for warning in result["warnings"]
    )
    assert "ROI" not in result["content"]


@pytest.mark.asyncio
async def test_legal_agent_warns_when_legal_kb_not_ready():
    result = await run_legal_agent(
        query="Sang ten so do can gi",
        evidence=[],
        preferences={},
        readiness={"legal": {"status": "not_ready"}},
    )

    assert result["agent_name"] == "legal_advisor"
    assert "chua san sang" in result["content"].lower()
    assert result["warnings"]


@pytest.mark.asyncio
async def test_project_agent_warns_when_ready_but_evidence_is_empty():
    result = await run_project_agent(
        query="Thong tin du an",
        evidence=[],
        preferences={},
        readiness={"projects": {"status": "ready"}},
    )

    assert result["agent_name"] == "project_agent"
    assert "chua co" in result["content"].lower()
    assert "thong tin du an lien quan" not in result["content"].lower()
    assert result["warnings"]
    assert result["sources"] == []


@pytest.mark.asyncio
async def test_legal_agent_warns_when_ready_but_evidence_is_empty():
    result = await run_legal_agent(
        query="Phap ly sang ten",
        evidence=[],
        preferences={},
        readiness={"legal": {"status": "ready"}},
    )

    assert result["agent_name"] == "legal_advisor"
    assert "chua co" in result["content"].lower()
    assert "thong tin phap ly tham khao" not in result["content"].lower()
    assert result["warnings"]
    assert result["sources"] == []


@pytest.mark.asyncio
async def test_investment_agent_includes_financial_disclaimer():
    result = await run_investment_agent(
        query="Dau tu can ho Quan 7",
        evidence=[],
        preferences={"risk_preferences": {"value": "conservative"}},
        readiness={"listings": {"status": "ready"}},
    )

    assert result["agent_name"] == "investment_advisor"
    assert "khong phai loi khuyen tai chinh" in result["content"].lower()


@pytest.mark.asyncio
async def test_synthesizer_node_deduplicates_warnings_and_ignores_unvalidated_sources():
    state = {
        "request": AgentChatRequest(
            request_id="req-1",
            session_id="session-1",
            message="Tim can ho",
            locale="vi-VN",
        ),
        "agents_to_run": ["property_search", "project_agent"],
        "warnings": ["shared_warning"],
        "agent_results": {
            "property_search": {
                "content": "Listing content",
                "warnings": ["shared_warning", "listing_warning"],
                "sources": [
                    {
                        "type": "listing",
                        "id": 1,
                        "product_id": "p-1",
                        "url": "https://example.test/1",
                        "title": "Can ho A",
                    },
                    {
                        "type": "listing",
                        "id": 1,
                        "product_id": "p-1",
                        "url": "https://example.test/1",
                        "title": "Can ho A",
                    },
                ],
            },
            "project_agent": {
                "content": "Project content",
                "warnings": ["listing_warning", "project_warning"],
                "sources": [
                    {
                        "type": "listing",
                        "id": 1,
                        "product_id": "p-1",
                        "url": "https://example.test/1",
                        "title": "Can ho A",
                    },
                    {
                        "type": "project",
                        "id": 2,
                        "product_id": "p-2",
                        "url": "https://example.test/2",
                        "title": "Du an B",
                    },
                ],
            },
        },
        "trace_steps": [],
    }

    result = await synthesizer_node(state)

    assert result["warnings"] == [
        "shared_warning",
        "listing_warning",
        "project_warning",
    ]
    assert result["sources"] == []


