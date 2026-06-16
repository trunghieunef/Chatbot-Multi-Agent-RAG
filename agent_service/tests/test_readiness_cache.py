from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_service import main
from agent_service.config import get_agent_settings
from agent_service.tools import readiness


@pytest.mark.asyncio
async def test_build_readiness_snapshot_uses_ttl_cache(monkeypatch):
    readiness.clear_readiness_cache()
    calls = {"count": 0}

    async def fake_count_source(source_name: str):
        calls["count"] += 1
        return {"status": "ready", "parent_count": 1, "chunk_count": 1}

    monkeypatch.setattr(readiness, "count_source", fake_count_source)

    first = await readiness.build_readiness_snapshot()
    second = await readiness.build_readiness_snapshot()

    assert first == second
    assert calls["count"] == len(readiness.SOURCE_NAMES)


def test_readiness_endpoint_returns_sources(monkeypatch):
    async def fake_snapshot():
        return {"listings": {"status": "ready", "parent_count": 1, "chunk_count": 1}}

    monkeypatch.setenv("AGENT_ALLOW_DEV_INTERNAL_KEY", "true")
    get_agent_settings.cache_clear()
    monkeypatch.setattr(main, "build_readiness_snapshot", fake_snapshot, raising=False)
    client = TestClient(main.app)
    response = client.get(
        "/internal/agent/readiness",
        headers={"X-Internal-Agent-Key": "dev-agent-internal-key"},
    )
    get_agent_settings.cache_clear()

    assert response.status_code == 200
    assert response.json()["sources"]["listings"]["status"] == "ready"
