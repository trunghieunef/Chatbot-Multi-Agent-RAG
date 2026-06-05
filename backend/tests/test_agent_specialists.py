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
from agent_service.contracts import AgentChatRequest
from agent_service.graph.nodes import synthesizer_node
from agent_service.llm.gemini import GeminiClient


@pytest.mark.asyncio
async def test_gemini_client_generation_methods_are_async_without_api_key():
    assert inspect.iscoroutinefunction(GeminiClient.generate_text)
    assert inspect.iscoroutinefunction(GeminiClient.generate_json)

    client = GeminiClient(api_key="")

    assert await client.generate_text("x") == ""
    assert await client.generate_json("x") == {}


@pytest.mark.asyncio
async def test_gemini_client_uses_worker_thread_when_api_key_is_set(monkeypatch):
    class FakeModels:
        def generate_content(self, *, model, contents):
            assert model == "model"
            assert contents == "hello"
            return types.SimpleNamespace(text="threaded response")

    class FakeClient:
        def __init__(self, *, api_key):
            assert api_key == "key"
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
    assert result["confidence"] >= 0.7


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


def test_synthesizer_node_deduplicates_warnings_and_sources():
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

    result = synthesizer_node(state)

    assert result["warnings"] == [
        "shared_warning",
        "listing_warning",
        "project_warning",
    ]
    assert [
        source.model_dump(mode="json", exclude_none=True) for source in result["sources"]
    ] == [
        {
            "type": "listing",
            "id": 1,
            "product_id": "p-1",
            "title": "Can ho A",
            "url": "https://example.test/1",
            "metadata": {},
        },
        {
            "type": "project",
            "id": 2,
            "product_id": "p-2",
            "title": "Du an B",
            "url": "https://example.test/2",
            "metadata": {},
        },
    ]
