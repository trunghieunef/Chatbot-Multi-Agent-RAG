from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib import error, request


PROJECT_ROOT_RAW = os.environ.get("PROJECT_ROOT", "/opt/project")
REPO_ROOT = Path(PROJECT_ROOT_RAW).resolve()
PIPELINE_WORKER_URL = os.environ.get("PIPELINE_WORKER_URL", "http://pipeline-worker:8200").rstrip("/")
PIPELINE_WORKER_DATA_ROOT = os.environ.get("PIPELINE_WORKER_DATA_ROOT", "/app/data")


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


def _translate_backend_path(value: Any) -> Any:
    if isinstance(value, list):
        return [_translate_backend_path(item) for item in value]
    if not isinstance(value, str):
        return value

    normalized = value.replace("\\", "/")
    project_root = PROJECT_ROOT_RAW.replace("\\", "/").rstrip("/")
    project_data_root = f"{project_root}/data"
    if normalized.startswith(f"{project_data_root}/"):
        relative = normalized.removeprefix(f"{project_data_root}/")
        return f"{PIPELINE_WORKER_DATA_ROOT.rstrip('/')}/{relative}"
    return value


def _translate_args(args: dict[str, Any]) -> dict[str, Any]:
    return {key: _translate_backend_path(value) for key, value in args.items()}


def _post_json(path: str, payload: dict[str, Any], timeout: int = 7200) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Agent-Key": os.environ.get("AGENT_INTERNAL_KEY", ""),
    }
    req = request.Request(
        f"{PIPELINE_WORKER_URL}{path}",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Pipeline Worker request failed: {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Pipeline Worker request failed: {exc}") from exc


def run_crawler(module: str, args: dict[str, Any], cwd: Path | None = None, timeout: int = 7200) -> str:
    response = _post_json(
        "/internal/pipeline/crawler",
        {"module": module, "args": _translate_args(args), "timeout": timeout},
        timeout=timeout + 30,
    )
    return str(response.get("stdout", ""))


def run_listings_ingestion(csv_path: str, batch_size: int = 50) -> dict[str, int]:
    response = _post_json(
        "/internal/pipeline/ingest/listings",
        {"csv_path": _translate_backend_path(csv_path), "batch_size": batch_size},
    )
    return response["result"]


def run_projects_ingestion(csv_path: str, batch_size: int = 25) -> dict[str, int]:
    response = _post_json(
        "/internal/pipeline/ingest/projects",
        {"csv_path": _translate_backend_path(csv_path), "batch_size": batch_size},
    )
    return response["result"]


def run_news_ingestion(csv_path: str) -> dict[str, int]:
    response = _post_json(
        "/internal/pipeline/ingest/news",
        {"csv_path": _translate_backend_path(csv_path)},
    )
    return response["result"]


def run_legal_ingestion() -> dict[str, int]:
    response = _post_json("/internal/pipeline/ingest/legal", {})
    return response["result"]


def run_deactivate_expired_listings() -> dict[str, int]:
    response = _post_json("/internal/pipeline/maintenance/deactivate-expired-listings", {})
    return response["result"]


def run_cleanup_expired_listing_chunks(retention_days: int = 60) -> dict[str, int]:
    response = _post_json(
        "/internal/pipeline/maintenance/cleanup-expired-listing-chunks",
        {"retention_days": retention_days},
    )
    return response["result"]
