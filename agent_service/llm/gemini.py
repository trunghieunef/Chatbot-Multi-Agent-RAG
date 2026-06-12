from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any

from agent_service.config import get_agent_settings


@dataclass(frozen=True)
class GeminiResult:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_agent_settings()
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self.timeout_seconds = settings.AGENT_LLM_TIMEOUT_SECONDS

    async def generate_text_with_usage(
        self,
        prompt: str,
        *,
        timeout_seconds: float | None = None,
    ) -> GeminiResult:
        if not self.api_key:
            return GeminiResult(text="")

        try:
            from google import genai

            client = genai.Client(api_key=self.api_key)

            def generate_sync():
                return client.models.generate_content(model=self.model, contents=prompt)

            response = await asyncio.wait_for(
                asyncio.to_thread(generate_sync),
                timeout=timeout_seconds or self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            return GeminiResult(text="")
        except Exception:
            return GeminiResult(text="")
        usage = getattr(response, "usage_metadata", None) or getattr(
            response,
            "usageMetadata",
            None,
        )
        return GeminiResult(
            text=response.text or "",
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )

    async def generate_text(self, prompt: str) -> str:
        result = await self.generate_text_with_usage(prompt)
        return result.text

    async def generate_json(self, prompt: str) -> dict[str, Any]:
        text = await self.generate_text(prompt)
        if not text:
            return {}

        try:
            parsed = json.loads(text)
        except JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
