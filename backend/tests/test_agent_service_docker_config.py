from pathlib import Path


def test_docker_compose_contains_agent_service():
    compose = Path("docker-compose.yml").read_text()

    assert "agent-service:" in compose
    assert "AGENT_INTERNAL_KEY" in compose
    assert "8100:8100" not in compose
    assert "http://agent-service:8100" in compose


def test_backend_waits_for_internal_agent_service():
    compose = Path("docker-compose.yml").read_text()

    assert "agent-service:\n        condition: service_healthy" in compose
    assert "CHATBOT_AGENT_SERVICE_ENABLED: ${CHATBOT_AGENT_SERVICE_ENABLED:-false}" in compose


def test_compose_referenced_dockerfiles_exist():
    assert Path("agent_service/Dockerfile").exists()
    assert Path("agent_service/requirements.txt").exists()
    assert Path("backend/Dockerfile").exists()
    assert Path("frontend/Dockerfile").exists()


def test_env_example_documents_agent_service_defaults():
    env_example = Path(".env.example").read_text()

    assert "AGENT_SERVICE_URL=http://agent-service:8100" in env_example
    assert "AGENT_INTERNAL_KEY=change-me-internal-agent-key" in env_example
    assert "CHATBOT_AGENT_SERVICE_ENABLED=false" in env_example
    assert "NEXT_PUBLIC_API_URL=/api/v1" in env_example


def test_frontend_rewrite_uses_internal_api_url_for_compose():
    next_config = Path("frontend/next.config.ts").read_text()

    assert "process.env.INTERNAL_API_URL" in next_config
    assert 'destination: `${internalApiUrl}/api/v1/:path*`' in next_config
