from __future__ import annotations

import pytest

from agent_service.contracts import AgentAction, AgentChatRequest, AgentContext
from agent_service.agents.legal_advisor_agent import LegalAdvisorAgent
from agent_service.agents.news_agent import NewsAgent
from agent_service.graph import agentic_workflow
from agent_service.tools.web import search_web


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeHTTP:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[dict] = []

    async def post(self, url, json=None):
        self.calls.append({"url": url, "json": json})
        return _FakeResponse(self.payload)


_TAVILY_PAYLOAD = {
    "results": [
        {"title": "Bài A", "url": "https://a.vn/1", "content": "nội dung A", "score": 0.9},
        {"title": "Bài B", "url": "https://b.vn/2", "content": "nội dung B", "score": 0.7},
    ]
}


@pytest.mark.asyncio
async def test_search_web_shapes_results_like_articles():
    out = await search_web("thủ tục sổ đỏ", api_key="k", client=_FakeHTTP(_TAVILY_PAYLOAD))
    assert out["status"] == "success"
    assert len(out["results"]) == 2 == len(out["evidence_ids"])
    first = out["results"][0]
    assert first["title"] == "Bài A"
    assert first["snippet"] == "nội dung A"
    assert first["citation"] == "https://a.vn/1"
    assert first["evidence_id"] == out["evidence_ids"][0]


@pytest.mark.asyncio
async def test_search_web_skips_without_key():
    out = await search_web("bất kỳ", api_key="")
    assert out["status"] == "skipped"
    assert out["results"] == []


def _empty_tool_action() -> AgentAction:
    return AgentAction(
        iteration=0, action_type="call_tool", status="success",
        tool_result={"status": "success", "results": [], "evidence_ids": []},
    )


def _ctx(agent: str, query: str) -> AgentContext:
    return AgentContext(agent_name=agent, query=query, normalized_query=query)


@pytest.mark.asyncio
async def test_news_agent_falls_back_to_web_when_kb_empty():
    thought = await NewsAgent().think(
        _ctx("news_agent", "tin tuc bat dong san"), 1, [_empty_tool_action()], []
    )
    assert thought.tool_name == "search_web"


@pytest.mark.asyncio
async def test_legal_agent_falls_back_to_web_when_kb_empty():
    thought = await LegalAdvisorAgent().think(
        _ctx("legal_advisor", "thu tuc sang ten so do"), 1, [_empty_tool_action()], []
    )
    assert thought.tool_name == "search_web"


class _LLMTextStub:
    async def generate_text(self, prompt):
        return "Theo Bài A, hôm nay trời nắng."


@pytest.mark.asyncio
async def test_off_topic_answers_from_web_then_steers_back(monkeypatch):
    async def fake_search_web(query, *, max_results=5, **kwargs):
        return {"status": "success",
                "results": [{"title": "Bài A", "url": "https://a.vn/1", "snippet": "trời nắng"}],
                "evidence_ids": ["ev_web_x_0"]}

    import agent_service.tools.web as web_mod
    monkeypatch.setattr(web_mod, "search_web", fake_search_web)
    monkeypatch.setattr(agentic_workflow, "_make_llm_client", lambda s: _LLMTextStub())

    state = {
        "request": AgentChatRequest(
            request_id="r", session_id="s", message="hôm nay thời tiết thế nào"
        ),
        "supervisor_plan": {"intent": "off_topic", "selected_agents": []},
        "_agent_results": {},
    }
    out = await agentic_workflow._node_synthesize(state)
    assert "trời nắng" in out["final_response"]
    assert "bất động sản" in out["final_response"]  # the steer-back line
    assert out["final_sources"]


@pytest.mark.asyncio
async def test_off_topic_degrades_to_refusal_without_web(monkeypatch):
    from agent_service.config import get_agent_settings
    monkeypatch.setattr(get_agent_settings(), "TAVILY_API_KEY", "")
    monkeypatch.setattr(agentic_workflow, "_make_llm_client", lambda s: None)

    state = {
        "request": AgentChatRequest(
            request_id="r", session_id="s", message="kể chuyện cười đi"
        ),
        "supervisor_plan": {"intent": "off_topic", "selected_agents": []},
        "_agent_results": {},
    }
    out = await agentic_workflow._node_synthesize(state)
    assert "bất động sản" in out["final_response"]
    assert out["final_sources"] == []
