from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph import router as router_mod
from agent_service.graph.router import RouterDecision, route_request


class _CapturingClient:
    def __init__(self):
        self.last_prompt = None

    async def generate_json(self, prompt, *, timeout_seconds=None):
        self.last_prompt = prompt
        return {"intent": "property_search", "agents": ["property_search"],
                "confidence": 0.9, "filters": {"district": "Quận 7"},
                "reason": "follow-up about district"}


@pytest.mark.asyncio
async def test_planner_prompt_includes_conversation_context(monkeypatch):
    monkeypatch.setenv("AGENT_ROUTER_MODE", "llm")
    from agent_service.config import get_agent_settings
    get_agent_settings.cache_clear()

    client = _CapturingClient()
    state = {
        "request": AgentChatRequest(
            request_id="r1", session_id="s1", message="thế còn quận 7?",
        ),
        "conversation_context": [
            {"role": "user", "content": "tìm căn hộ 2 phòng ngủ ở Hà Nội"},
            {"role": "assistant", "content": "Đây là vài lựa chọn ở Hà Nội..."},
        ],
    }
    decision = await route_request(state, client=client)
    get_agent_settings.cache_clear()

    assert isinstance(decision, RouterDecision)
    assert "quận 7" in client.last_prompt.lower()
    assert "phòng ngủ" in client.last_prompt.lower()  # prior turn is in the prompt
