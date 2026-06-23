from __future__ import annotations

import pytest

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentContext, ToolDef
from agent_service.llm.gemini import ToolLoopResult, ToolLoopStep
from agent_service.tools.registry import ToolRegistry
from agent_service.agents import fc_runner


def _registry_with_listings(results):
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="search_listings", description="x",
        parameters={"query": "str", "filters": "dict"},
        required_params=["query"], allowed_for=["property_search"],
    ))

    async def _search(**kwargs):
        return {"status": "success", "results": results,
                "evidence_ids": [f"ev_{r['id']}" for r in results]}

    reg.bind("search_listings", _search)
    return reg


class _FakeLLM:
    def __init__(self, text):
        self._text = text

    async def run_tool_loop(self, *, executor, **kwargs):
        # Simulate the model calling the tool once, then answering.
        result = await executor("search_listings", {"query": "căn hộ"})
        return ToolLoopResult(
            text=self._text,
            steps=[ToolLoopStep("search_listings", {"query": "căn hộ"}, result)],
            iterations=2,
        )


@pytest.mark.asyncio
async def test_run_specialist_uses_llm_text_and_build_result_sources():
    listings = [{"id": 1, "title": "Căn A", "price_text": "2 tỷ",
                 "area_text": "60 m²", "district": "Quận 7", "city": "HCM"}]
    reg = _registry_with_listings(listings)
    ctx = AgentContext(agent_name="property_search", query="Tìm căn hộ Quận 7",
                       normalized_query="tim can ho quan 7", routing_filters={"city": "HCM"})
    result = await fc_runner.run_specialist(
        agent_name="property_search", context=ctx, registry=reg,
        llm_client=_FakeLLM("Tôi gợi ý căn A vì gần trung tâm."),
        settings=get_agent_settings(),
    )
    assert result.agent_name == "property_search"
    assert result.status == "completed"
    assert "căn a" in result.content.lower()           # LLM analysis text
    assert any(s.id == 1 for s in result.sources)       # cards from build_result
    assert "ev_1" in result.evidence_ids_used


@pytest.mark.asyncio
async def test_run_specialist_falls_back_to_deterministic_without_llm():
    listings = [{"id": 2, "title": "Căn B", "price_text": "3 tỷ",
                 "area_text": "70 m²", "district": "Quận 1", "city": "HCM"}]
    reg = _registry_with_listings(listings)
    ctx = AgentContext(agent_name="property_search", query="Tìm căn hộ",
                       normalized_query="tim can ho", routing_filters={})
    result = await fc_runner.run_specialist(
        agent_name="property_search", context=ctx, registry=reg,
        llm_client=None, settings=get_agent_settings(),
    )
    assert result.status == "completed"
    assert any(s.id == 2 for s in result.sources)
