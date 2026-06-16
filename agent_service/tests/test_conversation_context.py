from __future__ import annotations

from agent_service.contracts import AgentChatRequest, ConversationContextItem
from agent_service.graph.nodes import context_builder
from agent_service.graph.router import _router_prompt


def test_context_builder_creates_compact_context():
    request = AgentChatRequest(
        request_id="req-context",
        session_id="session-1",
        message="Can ho nay co phap ly on khong?",
        conversation_context=[
            ConversationContextItem(role="user", content="Toi muon mua can ho Quan 7"),
            ConversationContextItem(role="assistant", content="Ban dang tim can ho Quan 7."),
        ],
    )

    result = context_builder({"request": request, "trace_steps": []})

    assert result["compact_context"] == [
        {"role": "user", "content": "Toi muon mua can ho Quan 7"},
        {"role": "assistant", "content": "Ban dang tim can ho Quan 7."},
    ]


def test_router_prompt_includes_compact_context():
    prompt = _router_prompt(
        "No co nen mua khong?",
        [{"role": "user", "content": "Dang noi ve can ho Quan 7"}],
    )

    assert "Dang noi ve can ho Quan 7" in prompt
