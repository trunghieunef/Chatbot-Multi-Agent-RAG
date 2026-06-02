from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class JsonCache:
    """Thin async JSON cache wrapper around a redis-compatible client."""

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
    payload = f"{namespace}|{text}" if namespace else text
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_pair(query: str, doc: str, *, namespace: str = "") -> str:
    payload = f"{namespace}|{query}|{doc}" if namespace else f"{query}|{doc}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_REDIS_CLIENT: Any = None


async def get_redis_client():
    global _REDIS_CLIENT
    if _REDIS_CLIENT is None:
        from redis import asyncio as redis_async

        from app.config import get_settings

        settings = get_settings()
        _REDIS_CLIENT = redis_async.from_url(settings.REDIS_URL, decode_responses=True)
    return _REDIS_CLIENT


async def reset_redis_client() -> None:
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        try:
            await _REDIS_CLIENT.aclose()
        except Exception:
            pass
        _REDIS_CLIENT = None
