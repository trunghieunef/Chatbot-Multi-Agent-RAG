from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_service.config import get_agent_settings
from agent_service.main import app


@pytest.fixture(autouse=True)
def clear_agent_settings_cache():
    get_agent_settings.cache_clear()
    yield
    get_agent_settings.cache_clear()


def test_agent_settings_defaults_are_internal_safe(monkeypatch):
    monkeypatch.chdir(Path(__file__).parent)
    monkeypatch.delenv("AGENT_INTERNAL_KEY", raising=False)
    monkeypatch.delenv("AGENT_ALLOW_DEV_INTERNAL_KEY", raising=False)
    settings = get_agent_settings()

    assert settings.AGENT_INTERNAL_KEY == "dev-agent-internal-key"
    assert settings.AGENT_ALLOW_DEV_INTERNAL_KEY is False
    assert settings.GEMINI_MODEL == "gemini-2.0-flash"
    assert settings.CHATBOT_TRACE_LEVEL == "full"


def test_internal_health_requires_agent_key(monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret-test-key")
    client = TestClient(app)

    response = client.get("/internal/agent/health")

    assert response.status_code == 401


def test_internal_health_accepts_agent_key(monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret-test-key")
    client = TestClient(app)

    response = client.get(
        "/internal/agent/health",
        headers={"X-Internal-Agent-Key": "secret-test-key"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "agent-service"


def test_internal_health_uses_current_agent_settings(monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret-test-key")
    monkeypatch.setenv("AGENT_GRAPH_VERSION", "agent-graph-test")
    client = TestClient(app)

    response = client.get(
        "/internal/agent/health",
        headers={"X-Internal-Agent-Key": "secret-test-key"},
    )

    assert response.status_code == 200
    assert response.json()["graph_version"] == "agent-graph-test"


def test_internal_health_rejects_default_key_without_dev_opt_in(monkeypatch):
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "dev-agent-internal-key")
    monkeypatch.delenv("AGENT_ALLOW_DEV_INTERNAL_KEY", raising=False)
    client = TestClient(app)

    response = client.get(
        "/internal/agent/health",
        headers={"X-Internal-Agent-Key": "dev-agent-internal-key"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Agent internal key is not configured securely"


def test_internal_health_rejects_env_example_placeholder_key(monkeypatch):
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "change-me-internal-agent-key")
    monkeypatch.delenv("AGENT_ALLOW_DEV_INTERNAL_KEY", raising=False)
    client = TestClient(app)

    response = client.get(
        "/internal/agent/health",
        headers={"X-Internal-Agent-Key": "change-me-internal-agent-key"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Agent internal key is not configured securely"


def test_internal_health_allows_default_key_with_dev_opt_in(monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "dev-agent-internal-key")
    monkeypatch.setenv("AGENT_ALLOW_DEV_INTERNAL_KEY", "true")
    client = TestClient(app)

    response = client.get(
        "/internal/agent/health",
        headers={"X-Internal-Agent-Key": "dev-agent-internal-key"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_internal_readiness_accepts_agent_key(monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret-test-key")
    client = TestClient(app)

    response = client.get(
        "/internal/agent/readiness",
        headers={"X-Internal-Agent-Key": "secret-test-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["sources"] == {}
