from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Callable

import httpx


INTENT_PROMPT = (
    "Bạn là bộ trích xuất tag bất động sản. "
    "Đọc mô tả sau và trả JSON dạng {{\"tags\": [\"...\"]}} "
    "với tối đa 8 tag ngắn gọn, viết thường, không trùng lặp. "
    "Nội dung: {content}"
)


@dataclass
class NominatimGeocoder:
    user_agent: str
    rate_limit_seconds: float = 1.0
    base_url: str = "https://nominatim.openstreetmap.org/search"
    client_factory: Callable[[], object] = field(default=lambda: httpx.AsyncClient(timeout=15))

    async def geocode(self, address: str) -> tuple[float, float] | None:
        if not address or not address.strip():
            return None

        async with self.client_factory() as client:
            response = await client.get(
                self.base_url,
                params={"q": address.strip(), "format": "json", "limit": 1},
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()
            data = response.json()

        if self.rate_limit_seconds > 0:
            await asyncio.sleep(self.rate_limit_seconds)

        if not data:
            return None

        try:
            return float(data[0]["lat"]), float(data[0]["lon"])
        except (KeyError, ValueError):
            return None


@dataclass
class GeminiIntentExtractor:
    api_key: str
    model: str = "gemini-2.0-flash"
    client: object | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            from google import genai

            if not self.api_key:
                raise ValueError("GEMINI_API_KEY required for intent extraction")
            self.client = genai.Client(api_key=self.api_key)

    async def extract(self, content: str) -> list[str]:
        if not content or not content.strip():
            return []
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model,
            contents=INTENT_PROMPT.format(content=content[:1500]),
        )
        try:
            payload = json.loads(response.text)
            tags = payload.get("tags", [])
            return [tag for tag in tags if isinstance(tag, str) and tag.strip()]
        except (json.JSONDecodeError, AttributeError, TypeError):
            return []
