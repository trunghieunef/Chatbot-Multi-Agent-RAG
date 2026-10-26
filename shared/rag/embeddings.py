"""Local dense embedding helpers for retrieval."""

from __future__ import annotations

import asyncio
import inspect
import os
from contextlib import contextmanager
from dataclasses import dataclass
from collections.abc import Iterator
from typing import Sequence


def _accepts_local_files_only(model_class: object) -> bool:
    try:
        parameters = inspect.signature(model_class.__init__).parameters
    except (TypeError, ValueError):
        return False
    return "local_files_only" in parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


@contextmanager
def _temporary_hf_offline(enabled: bool) -> Iterator[None]:
    if not enabled:
        yield
        return

    keys = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
    previous = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys:
            os.environ[key] = "1"
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@dataclass
class BGEEmbedder:
    """Sentence-transformers wrapper for BAAI/bge-m3 dense embeddings."""

    model_name: str = "BAAI/bge-m3"
    batch_size: int = 16
    retries: int = 3
    retry_delay_seconds: float = 1.0
    embedding_dim: int = 1024
    normalize_embeddings: bool = True
    max_seq_length: int = 8192
    device: str | None = None
    local_files_only: bool = False
    model: object | None = None
    provider: str = "bge_m3"

    def __post_init__(self) -> None:
        if self.model is None:
            with _temporary_hf_offline(self.local_files_only):
                from sentence_transformers import SentenceTransformer

                kwargs = {"device": self.device} if self.device else {}
                supports_local_only = _accepts_local_files_only(SentenceTransformer)
                if self.local_files_only and supports_local_only:
                    kwargs["local_files_only"] = True
                self.model = SentenceTransformer(self.model_name, **kwargs)
        if hasattr(self.model, "max_seq_length"):
            self.model.max_seq_length = self.max_seq_length

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        clean_texts = [text for text in texts if text and text.strip()]
        if not clean_texts:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(clean_texts), self.batch_size):
            batch = clean_texts[start : start + self.batch_size]
            vectors.extend(await self._embed_batch_with_retry(batch))
        return vectors

    async def _embed_batch_with_retry(self, batch: Sequence[str]) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                return await asyncio.to_thread(self._embed_batch_sync, batch)
            except Exception as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    await asyncio.sleep(self.retry_delay_seconds * (2**attempt))
        raise RuntimeError(f"Embedding failed after {self.retries} attempts") from last_error

    def _embed_batch_sync(self, batch: Sequence[str]) -> list[list[float]]:
        encoded = self.model.encode(
            list(batch),
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
        )
        vectors = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        result = [list(vector) for vector in vectors]
        for vector in result:
            if len(vector) != self.embedding_dim:
                raise ValueError(
                    f"Expected embedding dimension {self.embedding_dim}, got {len(vector)}"
                )
        return result
