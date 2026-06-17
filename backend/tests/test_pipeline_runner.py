import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/ "airflow"))

from plugins.pipeline_runner import (
    build_crawler_command,
    run_crawler,
    run_listings_ingestion,
)


def test_build_crawler_command_assembles_module_and_args():
    cmd = build_crawler_command(
        module="crawler.sale.crawl_urls",
        args={"--pages": ["1", "10"], "--output": "data/raw/sale_urls.csv", "--workers": "4"},
    )

    assert cmd[:3] == [sys.executable, "-m", "crawler.sale.crawl_urls"]
    assert "--pages" in cmd and "1" in cmd and "10" in cmd
    assert "--output" in cmd and "data/raw/sale_urls.csv" in cmd


def test_run_crawler_posts_to_pipeline_worker_and_translates_data_paths(monkeypatch):
    from plugins import pipeline_runner

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"stdout": "ok", "stderr": ""}'

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["payload"] = req.data.decode("utf-8")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("AGENT_INTERNAL_KEY", "test-key")
    monkeypatch.setattr(pipeline_runner.request, "urlopen", fake_urlopen)

    output = run_crawler(
        module="crawler.sale.crawl_urls",
        args={"--output": "/opt/project/data/raw/sale_urls.csv"},
        timeout=10,
    )

    assert output == "ok"
    assert captured["url"] == "http://pipeline-worker:8200/internal/pipeline/crawler"
    assert captured["headers"]["X-internal-agent-key"] == "test-key"
    assert captured["timeout"] == 40
    assert '"--output": "/app/data/raw/sale_urls.csv"' in captured["payload"]


def test_run_listings_ingestion_posts_to_pipeline_worker(monkeypatch):
    from plugins import pipeline_runner

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return (
                b'{"result": {"published": 2, "indexed": 2, "chunks": 8, '
                b'"publish_errors": 0, "index_errors": 0}}'
            )

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["payload"] = req.data.decode("utf-8")
        return FakeResponse()

    monkeypatch.setattr(pipeline_runner.request, "urlopen", fake_urlopen)

    result = run_listings_ingestion("/opt/project/data/raw/sale_details.csv", batch_size=25)

    assert captured["url"] == "http://pipeline-worker:8200/internal/pipeline/ingest/listings"
    assert '"csv_path": "/app/data/raw/sale_details.csv"' in captured["payload"]
    assert '"batch_size": 25' in captured["payload"]
    assert result["published"] == 2
    assert result["chunks"] == 8


def test_run_legal_ingestion_callable_exists():
    from plugins import pipeline_runner

    assert hasattr(pipeline_runner, "run_legal_ingestion")
    assert callable(pipeline_runner.run_legal_ingestion)
