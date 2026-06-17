import asyncio
import uuid
from types import SimpleNamespace

from fastapi import HTTPException

from app.config import get_settings
from app.services.chatbot.quota import enforce_chat_quota


class FakeCountResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class CountingDB:
    def __init__(self, count):
        self.count = count
        self.queries = []
        self.params = []

    async def execute(self, query, params=None):
        self.queries.append(query)
        self.params.append(params or {})
        return FakeCountResult(self.count)


def test_authenticated_quota_blocks_at_limit(monkeypatch):
    monkeypatch.setenv("AUTH_CHAT_DAILY_LIMIT", "1")
    get_settings.cache_clear()
    db = CountingDB(count=1)

    try:
        asyncio.run(
            enforce_chat_quota(
                db,
                user=SimpleNamespace(id=42),
                session_id=uuid.uuid4(),
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 429
        assert "gioi han" in exc.detail.lower()
    else:
        raise AssertionError("expected authenticated quota rejection")


def test_authenticated_below_limit_does_not_raise(monkeypatch):
    monkeypatch.setenv("AUTH_CHAT_DAILY_LIMIT", "2")
    get_settings.cache_clear()
    db = CountingDB(count=1)

    asyncio.run(
        enforce_chat_quota(
            db,
            user=SimpleNamespace(id=42),
            session_id=uuid.uuid4(),
        )
    )

    assert len(db.queries) == 2


def test_anonymous_existing_session_blocks_at_limit(monkeypatch):
    monkeypatch.setenv("ANON_CHAT_DAILY_LIMIT", "1")
    get_settings.cache_clear()
    session_id = uuid.uuid4()
    db = CountingDB(count=1)

    try:
        asyncio.run(enforce_chat_quota(db, user=None, session_id=session_id))
    except HTTPException as exc:
        assert exc.status_code == 429
        assert "ngay" in exc.detail.lower()
    else:
        raise AssertionError("expected anonymous quota rejection")


def test_quota_counts_user_messages_only(monkeypatch):
    monkeypatch.setenv("AUTH_CHAT_DAILY_LIMIT", "5")
    get_settings.cache_clear()
    db = CountingDB(count=4)

    asyncio.run(
        enforce_chat_quota(
            db,
            user=SimpleNamespace(id=42),
            session_id=uuid.uuid4(),
        )
    )

    query_text = str(db.queries[-1])
    assert "chat_messages" in query_text
    assert "chat_sessions" in query_text
    assert "role" in query_text
    assert db.count == 4


def test_quota_acquires_transaction_lock_before_counting(monkeypatch):
    monkeypatch.setenv("AUTH_CHAT_DAILY_LIMIT", "5")
    get_settings.cache_clear()
    db = CountingDB(count=0)

    asyncio.run(
        enforce_chat_quota(
            db,
            user=SimpleNamespace(id=42),
            session_id=uuid.uuid4(),
        )
    )

    assert len(db.queries) == 2
    lock_query = str(db.queries[0])
    assert "pg_advisory_xact_lock" in lock_query
    assert "hashtext" in lock_query
    assert db.params[0]["lock_key"].startswith("chat-quota:")
    assert "auth:42" in db.params[0]["lock_key"]
