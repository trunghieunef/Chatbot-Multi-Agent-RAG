from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def compute_sha256(path: str) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _log_path(digest: str, log_dir: str) -> Path:
    return Path(log_dir) / f"{digest}.json"


def has_been_ingested(digest: str, log_dir: str) -> bool:
    return _log_path(digest, log_dir).exists()


def mark_ingested(digest: str, log_dir: str, *, info: dict[str, Any] | None = None) -> None:
    os.makedirs(log_dir, exist_ok=True)
    payload = {"digest": digest, "info": info or {}}
    _log_path(digest, log_dir).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    