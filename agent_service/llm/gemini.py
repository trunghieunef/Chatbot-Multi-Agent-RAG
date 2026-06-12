from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any

from agent_service.config import get_agent_settings
from agent_service.llm.cost import get_runtime_cost_summary, record_runtime_llm_cost


@dataclass(frozen=True)
class GeminiResult:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float = 0.0
    skipped_reason: str | None = None


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_agent_settings()
        self.settings = settings
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model_explicitly_configured = (
            model is not None or "GEMINI_MODEL" in settings.model_fields_set
        )
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
        if not self.model_explicitly_configured:
            return GeminiResult(text="", skipped_reason="gemini_model_not_configured")

        if self.settings.AGENT_LLM_COST_TRACKING_ENABLED:
            summary = get_runtime_cost_summary(self.settings)
            if not summary.get("tracking_available", True):
                return GeminiResult(
                    text="",
                    skipped_reason="llm_cost_tracking_unavailable",
                )
            if summary.get("budget_exceeded"):
                return GeminiResult(text="", skipped_reason="llm_budget_exceeded")

        try:
            from google import genai

            timeout = timeout_seconds or self.timeout_seconds
            http_options = {"timeout": int(timeout * 1000)}
            client = genai.Client(api_key=self.api_key, http_options=http_options)

            def generate_sync():
                return client.models.generate_content(model=self.model, contents=prompt)

            response = await asyncio.wait_for(
                asyncio.to_thread(generate_sync),
                timeout=timeout,
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
            input_tokens=(input_tokens := getattr(usage, "prompt_token_count", None)),
            output_tokens=(
                output_tokens := getattr(usage, "candidates_token_count", None)
            ),
            estimated_cost_usd=record_runtime_llm_cost(
                self.settings,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
        )

    async def generate_text(self, prompt: str) -> str:
        result = await self.generate_text_with_usage(prompt)
        return result.text

    async def generate_json(
        self,
        prompt: str,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        result = await self.generate_text_with_usage(
            prompt,
            timeout_seconds=timeout_seconds,
        )
        text = result.text
        if not text:
            return {}

        try:
            parsed = json.loads(text)
        except JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
