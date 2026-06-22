from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any

from agent_service.config import get_agent_settings
from agent_service.llm.cost import get_runtime_cost_summary, record_runtime_llm_cost

logger = logging.getLogger(__name__)

# Limit concurrent Gemini calls to avoid 429 rate limits
_MAX_CONCURRENT_LLM_CALLS = 2
_llm_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_LLM_CALLS)


@dataclass(frozen=True)
class GeminiResult:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float = 0.0
    skipped_reason: str | None = None
    error_message: str | None = None


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

    async def _call_gemini_with_retry(
        self,
        prompt: str,
        timeout_seconds: float,
        max_retries: int = 3,
    ):
        """Call Gemini with exponential backoff retry for 429 errors."""
        from google import genai
        import google.api_core.exceptions as google_exceptions

        http_options = {"timeout": int(timeout_seconds * 1000)}
        client = genai.Client(api_key=self.api_key, http_options=http_options)

        last_error = None
        for attempt in range(max_retries):
            try:
                def generate_sync():
                    return client.models.generate_content(
                        model=self.model, contents=prompt
                    )

                return await asyncio.wait_for(
                    asyncio.to_thread(generate_sync),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                last_error = "timeout"
                logger.warning(
                    "Gemini call timed out after %ss (attempt %d/%d)",
                    timeout_seconds, attempt + 1, max_retries,
                )
            except google_exceptions.ResourceExhausted:
                # 429 - rate limit
                last_error = "429_rate_limit"
                wait = min(2 ** attempt, 8)
                logger.warning(
                    "Gemini 429 rate limit (attempt %d/%d), waiting %ds...",
                    attempt + 1, max_retries, wait,
                )
                await asyncio.sleep(wait)
            except google_exceptions.InvalidArgument as e:
                # 400 - bad request (don't retry)
                logger.error("Gemini 400 Bad Request: %s", str(e)[:300])
                raise
            except Exception as e:
                last_error = str(e)[:200]
                logger.error(
                    "Gemini call failed (attempt %d/%d): %s",
                    attempt + 1, max_retries, last_error,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)

        raise RuntimeError(f"Gemini call failed after {max_retries} retries: {last_error}")

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

        timeout = timeout_seconds or self.timeout_seconds
        try:
            async with _llm_semaphore:
                response = await self._call_gemini_with_retry(
                    prompt, timeout_seconds=timeout,
                )
        except RuntimeError as e:
            logger.error("Gemini call ultimately failed: %s", e)
            return GeminiResult(text="", error_message=str(e)[:500])
        except Exception as e:
            logger.error("Gemini unexpected error: %s", e)
            return GeminiResult(text="", error_message=str(e)[:500])
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
