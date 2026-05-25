from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(os.environ.get("PROJECT_ROOT", "/opt/project")).resolve()


def build_crawler_command(module: str, args: dict[str, Any]) -> list[str]:
    cmd: list[str] = [sys.executable, "-m", module]
    for flag, value in args.items():
        if isinstance(value, list):
            cmd.append(flag)
            cmd.extend(str(item) for item in value)
        elif value is None or value == "":
            continue
        else:
            cmd.extend([flag, str(value)])
    return cmd


def run_crawler(module: str, args: dict[str, Any], cwd: Path | None = None, timeout: int = 7200) -> str:
    cmd = build_crawler_command(module, args)
    completed = subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{module} exit code {completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed.stdout


def run_listings_ingestion(csv_path: str, batch_size: int = 50) -> dict[str, int]:
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    import asyncio

    from data_pipeline.ingestors.listings_ingestor import load_csv_to_db

    return asyncio.run(load_csv_to_db(csv_path, batch_size=batch_size))


def run_projects_ingestion(csv_path: str, batch_size: int = 25) -> dict[str, int]:
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    import asyncio
    import csv as csvlib

    from data_pipeline.ingestors.projects_ingestor import ingest_project_rows

    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csvlib.DictReader(handle))
    return asyncio.run(ingest_project_rows(rows, batch_size=batch_size))


def run_news_ingestion(csv_path: str) -> dict[str, int]:
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    import asyncio
    import csv as csvlib

    from data_pipeline.ingestors.news_ingestor import ingest_article_rows

    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csvlib.DictReader(handle))
    return asyncio.run(ingest_article_rows(rows))
