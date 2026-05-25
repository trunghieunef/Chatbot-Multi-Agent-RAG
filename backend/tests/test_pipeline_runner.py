import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/ "airflow"))

from plugins.pipeline_runner import build_crawler_command, run_crawler


def test_build_crawler_command_assembles_module_and_args():
    cmd = build_crawler_command(
        module="crawler.sale.crawl_urls",
        args={"--pages": ["1", "10"], "--output": "data/raw/sale_urls.csv", "--workers": "4"},
    )

    assert cmd[:3] == [sys.executable, "-m", "crawler.sale.crawl_urls"]
    assert "--pages" in cmd and "1" in cmd and "10" in cmd
    assert "--output" in cmd and "data/raw/sale_urls.csv" in cmd


def test_run_crawler_raises_when_subprocess_fails(monkeypatch):
    class FakeCompleted:
        returncode = 2
        stdout = "boom"
        stderr = "stderr boom"

    def fake_run(cmd, **kwargs):
        return FakeCompleted()

    monkeypatch.setattr("plugins.pipeline_runner.subprocess.run", fake_run)

    with pytest.raises(RuntimeError) as exc:
        run_crawler(module="crawler.sale.crawl_urls", args={})

    assert "exit code 2" in str(exc.value)
