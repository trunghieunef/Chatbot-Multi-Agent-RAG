from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@dataclass
class JsonCache:
    """Thin async JSON cache wrapper around a redis-compatible client.

    Namespacing prevents key collisions between callers; ``ttl_seconds`` is
    applied per ``set`` call so different cache instances can use different
    expirations against the same Redis backend.
    """

    client: Any
    namespace: str
    ttl_seconds: int | None = None

    def _key(self, raw: str) -> str:
        return f"{self.namespace}:{raw}"

    async def get(self, key: str) -> Any:
        raw = await self.client.get(self._key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None

    async def set(self, key: str, value: Any) -> None:
        await self.client.set(
            self._key(key),
            json.dumps(value, ensure_ascii=False),
            ex=self.ttl_seconds,
        )


def hash_text(text: str, *, namespace: str = "") -> str:
    """Hash a single text. Pass ``namespace`` to scope it to a model/version
    so cache hits never bleed across embedding model upgrades."""
    payload = f"{namespace}|{text}" if namespace else text
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_pair(query: str, doc: str, *, namespace: str = "") -> str:
    """Hash a (query, doc) pair, optionally scoped to a model/version."""
    payload = f"{namespace}|{query}|{doc}" if namespace else f"{query}|{doc}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_redis_client():
    from app.config import get_settings
    from redis import asyncio as redis_async

    settings = get_settings()
    return redis_async.from_url(settings.REDIS_URL, decode_responses=True)
