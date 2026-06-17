import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from pipeline_worker import runner, security
from pipeline_worker.main import app


def test_build_module_command_expands_flags_and_lists():
    cmd = runner.build_module_command(
        "crawler.sale.crawl_urls",
        {"--pages": ["1", "2"], "--output": "/app/data/raw/sale_urls.csv", "--empty": ""},
    )

    assert cmd[1:] == [
        "-m",
        "crawler.sale.crawl_urls",
        "--pages",
        "1",
        "2",
        "--output",
        "/app/data/raw/sale_urls.csv",
    ]


def test_parse_result_accepts_python_dict_output():
    result = runner.parse_result(
        "{'published': 1, 'indexed': 1, 'chunks': 4, 'publish_errors': 0, 'index_errors': 0}\n"
    )

    assert result["published"] == 1
    assert result["chunks"] == 4


def test_internal_key_is_required(monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret")

    with pytest.raises(HTTPException) as exc:
        security.require_internal_key("wrong")

    assert exc.value.status_code == 403


def test_health_endpoint():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_internal_health_endpoint():
    client = TestClient(app)

    response = client.get("/internal/pipeline/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "pipeline-worker"}


def test_crawler_endpoint_uses_runner(monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret")

    def fake_run_module(module, args, timeout=7200):
        assert module == "crawler.sale.crawl_urls"
        assert args == {"--pages": ["1"]}
        assert timeout == 123
        return runner.ModuleResult(stdout="done", stderr="")

    monkeypatch.setattr(runner, "run_module", fake_run_module)
    client = TestClient(app)

    response = client.post(
        "/internal/pipeline/crawler",
        headers={"X-Internal-Agent-Key": "secret"},
        json={"module": "crawler.sale.crawl_urls", "args": {"--pages": ["1"]}, "timeout": 123},
    )

    assert response.status_code == 200
    assert response.json() == {"stdout": "done", "stderr": ""}
