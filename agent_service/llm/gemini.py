from __future__ import annotations

import asyncio
import json
from json import JSONDecodeError
from typing import Any

from agent_service.config import get_agent_settings


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_agent_settings()
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self.timeout_seconds = settings.AGENT_LLM_TIMEOUT_SECONDS

    async def generate_text(self, prompt: str) -> str:
        if not self.api_key:
            return ""

        try:
            from google import genai

            client = genai.Client(api_key=self.api_key)

            def generate_sync():
                return client.models.generate_content(model=self.model, contents=prompt)

            response = await asyncio.wait_for(
                asyncio.to_thread(generate_sync),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            return ""
        except Exception:
            return ""
        return response.text or ""

    async def generate_json(self, prompt: str) -> dict[str, Any]:
        text = await self.generate_text(prompt)
        if not text:
            return {}

        try:
            parsed = json.loads(text)
        except JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
