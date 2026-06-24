from __future__ import annotations

import pytest

from agent_service.graph import router


def test_router_prompt_injects_db_property_types():
    """The router prompt must list the real Vietnamese property_type values from
    the DB (not hardcoded English) so the LLM emits values that match the data."""
    vocab = ["Căn hộ chung cư", "Nhà riêng", "Đất nền"]
    prompt = router._router_prompt("tìm căn hộ quận 7", None, vocab)

    for value in vocab:
        assert value in prompt
    # The old hardcoded English enum must be gone.
    assert "apartment, house, land, shophouse" not in prompt


def test_router_prompt_falls_back_to_vietnamese_instruction_without_vocab():
    """With no vocabulary available, the prompt must NOT order an English
    translation; it keeps the user's Vietnamese phrasing."""
    prompt = router._router_prompt("tìm căn hộ quận 7", None, [])
    assert "apartment, house, land, shophouse" not in prompt
    # Instruction stays Vietnamese-native.
    assert "property_type" in prompt


@pytest.mark.asyncio
async def test_get_property_type_vocabulary_caches(monkeypatch):
    """The taxonomy is read from the DB once and cached within the TTL."""
    router._PROPERTY_TYPE_VOCAB_CACHE = None
    calls = {"n": 0}

    async def fake_fetch():
        calls["n"] += 1
        return ["Căn hộ chung cư", "Đất nền"]

    monkeypatch.setattr(router, "_fetch_distinct_property_types", fake_fetch)

    first = await router.get_property_type_vocabulary(ttl_seconds=3600)
    second = await router.get_property_type_vocabulary(ttl_seconds=3600)

    assert first == ["Căn hộ chung cư", "Đất nền"]
    assert second == first
    assert calls["n"] == 1  # cached, queried only once
    router._PROPERTY_TYPE_VOCAB_CACHE = None


@pytest.mark.asyncio
async def test_get_property_type_vocabulary_degrades_on_db_error(monkeypatch):
    """A DB failure must not break routing — it degrades to an empty list."""
    router._PROPERTY_TYPE_VOCAB_CACHE = None

    async def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(router, "_fetch_distinct_property_types", boom)
    assert await router.get_property_type_vocabulary() == []
    router._PROPERTY_TYPE_VOCAB_CACHE = None
