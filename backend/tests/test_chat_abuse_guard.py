import uuid
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app.routers import chat
from app.services.chatbot.abuse_guard import (
    ChatAbuseGuard,
    enforce_chat_abuse_guard,
)


def test_abuse_guard_blocks_after_threshold():
    now = [100.0]
    guard = ChatAbuseGuard(max_requests=2, window_seconds=60, clock=lambda: now[0])

    assert guard.check("anon:session").allowed is True
    assert guard.check("anon:session").allowed is True
    blocked = guard.check("anon:session")

    assert blocked.allowed is False
    assert blocked.retry_after_seconds > 0


def test_abuse_guard_resets_after_window_passes():
    now = [100.0]
    guard = ChatAbuseGuard(max_requests=1, window_seconds=60, clock=lambda: now[0])

    assert guard.check("user:42").allowed is True
    assert guard.check("user:42").allowed is False

    now[0] = 161.0

    assert guard.check("user:42").allowed is True


def test_abuse_guard_prunes_expired_and_caps_keys():
    now = [100.0]
    guard = ChatAbuseGuard(
        max_requests=1,
        window_seconds=60,
        clock=lambda: now[0],
        max_keys=2,
    )

    assert guard.check("expired").allowed is True
    now[0] = 161.0
    assert guard.check("first").allowed is True
    assert guard.check("second").allowed is True
    assert guard.check("third").allowed is True

    assert "expired" not in guard._requests
    assert len(guard._requests) <= 2


def test_disabled_abuse_guard_helper_allows_request():
    response = SimpleNamespace(headers={})
    guard = ChatAbuseGuard(max_requests=0, window_seconds=60, clock=lambda: 100.0)

    enforce_chat_abuse_guard(
        guard,
        key="anon:ip:127.0.0.1",
        enabled=False,
        response=response,
    )

    assert response.headers == {}


def test_abuse_guard_helper_sets_retry_after_when_blocked():
    response = SimpleNamespace(headers={})
    guard = ChatAbuseGuard(max_requests=1, window_seconds=60, clock=lambda: 100.0)
    enforce_chat_abuse_guard(
        guard,
        key="auth:42",
        enabled=True,
        response=response,
    )

    try:
        enforce_chat_abuse_guard(
            guard,
            key="auth:42",
            enabled=True,
            response=response,
        )
    except HTTPException as exc:
        assert exc.status_code == 429
        assert response.headers["Retry-After"] == "60"
        assert exc.headers["Retry-After"] == "60"
        assert "thu lai" in exc.detail.lower()
    else:
        raise AssertionError("expected abuse guard rejection")


def test_anonymous_abuse_key_uses_ip_even_when_session_id_is_rotated():
    request = Request({"type": "http", "client": ("203.0.113.10", 12345)})
    first = chat._chat_abuse_key(
        SimpleNamespace(session_id=uuid.uuid4()),
        user=None,
        request=request,
    )
    second = chat._chat_abuse_key(
        SimpleNamespace(session_id=uuid.uuid4()),
        user=None,
        request=request,
    )

    assert first == "anon:ip:203.0.113.10"
    assert second == first
