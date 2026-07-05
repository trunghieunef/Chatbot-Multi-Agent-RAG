"""Regression: GET /chat/sessions/{id} 500'd with NameError: split_agents.

get_session_history falls back to `split_agents(m.agent_used)` when a stored
assistant message has no metadata_json['agents_used'] (the common case for
older messages), but split_agents was never imported into chat.py — so opening
any such session history raised NameError, the frontend caught the 500 and
deleted the conversation, and it vanished on refresh.
"""
from app.routers import chat as chat_router


def test_split_agents_is_resolvable_in_chat_router():
    # The name the endpoint calls must exist in the module namespace.
    assert hasattr(chat_router, "split_agents"), (
        "split_agents used in get_session_history but not imported into chat.py"
    )


def test_split_agents_handles_the_fallback_inputs():
    # Exactly the shapes get_session_history feeds it: a stored agent string,
    # a comma-joined string, and None.
    split = chat_router.split_agents
    assert split("property_search") == ["property_search"]
    assert split("property_search,legal_advisor") == [
        "property_search",
        "legal_advisor",
    ]
    assert split(None) == []
