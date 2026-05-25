from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Sequence

from google import genai


@dataclass
class GeminiEmbedder:
    api_key: str
    model: str = "gemini-embedding-001"
    batch_size: int = 100
    retries: int = 3
    retry_delay_seconds: float = 1.0
    output_dimensionality: int = 768
    client: object | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY is required for embeddings")
            self.client = genai.Client(api_key=self.api_key)

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
        from google.genai import types

        result = self.client.models.embed_content(
            model=self.model,
            contents=list(batch),
            config=types.EmbedContentConfig(output_dimensionality=self.output_dimensionality),
        )
        return [list(item.values) for item in result.embeddings]
