import pytest

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentChatRequest
from agent_service.graph.query_understanding import (
    build_query_understanding,
    merge_query_filters,
)


def test_current_query_filter_overrides_llm_inferred_filter():
    deterministic = {"district": "Quan 7"}
    llm = {"district": "Quan 2", "max_price": 5000000000}

    merged = merge_query_filters(deterministic, llm)

    assert merged["district"] == "Quan 7"
    assert merged["max_price"] == 5000000000


@pytest.mark.asyncio
async def test_query_understanding_uses_query_timeout(monkeypatch):
    monkeypatch.setenv("AGENT_QUERY_REWRITE_ENABLED", "true")
    monkeypatch.setenv("AGENT_LLM_QUERY_TIMEOUT_SECONDS", "1.75")
    get_agent_settings.cache_clear()
    seen = {}

    class FakeClient:
        async def generate_json(self, prompt, *, timeout_seconds=None):
            seen["timeout_seconds"] = timeout_seconds
            return {
                "rewritten_query": "tim can ho quan 7",
                "expanded_queries": [],
                "filters": {},
                "missing_slots": [],
            }

    await build_query_understanding(
        {
            "normalized_query": "tim can ho quan 7",
            "request": AgentChatRequest(
                request_id="req-query-timeout",
                message="tim can ho quan 7",
                session_id="session-1",
            ),
        },
        client=FakeClient(),
    )

    assert seen["timeout_seconds"] == 1.75
    get_agent_settings.cache_clear()


@pytest.mark.asyncio
async def test_query_understanding_prompt_includes_compact_context(monkeypatch):
    monkeypatch.setenv("AGENT_QUERY_REWRITE_ENABLED", "true")
    get_agent_settings.cache_clear()
    seen = {}

    class FakeClient:
        async def generate_json(self, prompt, *, timeout_seconds=None):
            seen["prompt"] = prompt
            return {
                "rewritten_query": "can ho quan 7 phap ly",
                "expanded_queries": [],
                "filters": {},
                "missing_slots": [],
            }

    await build_query_understanding(
        {
            "normalized_query": "can ho nay phap ly on khong",
            "compact_context": [
                {"role": "user", "content": "Dang noi ve can ho Quan 7"},
            ],
            "request": AgentChatRequest(
                request_id="req-query-context",
                message="No phap ly on khong?",
                session_id="session-1",
            ),
        },
        client=FakeClient(),
    )

    assert "Dang noi ve can ho Quan 7" in seen["prompt"]
    get_agent_settings.cache_clear()
