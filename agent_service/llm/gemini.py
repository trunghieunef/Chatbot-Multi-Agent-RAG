from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any

from google import genai
from google.genai import types

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


@dataclass(frozen=True)
class ToolLoopStep:
    tool_name: str
    args: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True)
class ToolLoopResult:
    text: str
    steps: list["ToolLoopStep"]
    iterations: int
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

    async def _call_gemini_with_retry(
        self,
        prompt: str,
        timeout_seconds: float,
        max_retries: int = 2,
    ):
        """Call Gemini with exponential backoff retry for rate-limit errors."""
        from google import genai

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
                    "Gemini timeout after %ss (attempt %d/%d)",
                    timeout_seconds, attempt + 1, max_retries,
                )
            except Exception as e:
                err_str = str(e)[:500]
                last_error = err_str
                # 400 errors: don't retry
                if "400" in err_str or "InvalidArgument" in err_str or "INVALID_ARGUMENT" in err_str:
                    logger.error("Gemini 400 Bad Request (not retrying): %s", err_str)
                    raise
                # 429 or other transient errors: retry with backoff
                is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "ResourceExhausted" in err_str
                wait = min(2 ** attempt, 8) if is_rate_limit else 1
                logger.warning(
                    "Gemini error (attempt %d/%d, %s): %s",
                    attempt + 1, max_retries,
                    "rate_limit" if is_rate_limit else "transient",
                    err_str[:200],
                )
                await asyncio.sleep(wait)

        raise RuntimeError(f"Gemini failed after {max_retries} retries: {last_error}")

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

        # Strip markdown code blocks if present
        text = text.strip()
        if text.startswith("```"):
            # Remove ```json or ``` and trailing ```
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            parsed = json.loads(text)
        except JSONDecodeError:
            # Try to extract first JSON object with regex
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except JSONDecodeError:
                    return {}
            else:
                return {}
        return parsed if isinstance(parsed, dict) else {}

    async def run_tool_loop(
        self,
        *,
        system_prompt: str,
        user_message: str,
        function_declarations: list[Any],
        executor: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
        max_iterations: int,
        timeout_seconds: float,
    ) -> ToolLoopResult:
        """Run a native function-calling ReAct loop.

        Each turn: ask the model; if it returns function calls, execute them via
        `executor`, append the results, and loop; otherwise return the final text.
        Does NOT gate on model_explicitly_configured (config validation already
        enforces an explicit model when live LLM is enabled).
        """
        if not self.api_key:
            return ToolLoopResult(text="", steps=[], iterations=0, skipped_reason="no_api_key")

        tools = [types.Tool(function_declarations=function_declarations)]
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=tools,
        )
        contents: list[Any] = [
            types.Content(role="user", parts=[types.Part(text=user_message)])
        ]
        steps: list[ToolLoopStep] = []
        http_options = {"timeout": int(timeout_seconds * 1000)}
        client = genai.Client(api_key=self.api_key, http_options=http_options)

        final_text = ""
        iteration = 0
        for iteration in range(1, max_iterations + 1):
            def _generate_sync(_contents=contents):
                return client.models.generate_content(
                    model=self.model, contents=_contents, config=config
                )

            async with _llm_semaphore:
                response = await asyncio.wait_for(
                    asyncio.to_thread(_generate_sync), timeout=timeout_seconds
                )

            usage = getattr(response, "usage_metadata", None)
            record_runtime_llm_cost(
                self.settings,
                input_tokens=getattr(usage, "prompt_token_count", None),
                output_tokens=getattr(usage, "candidates_token_count", None),
            )

            function_calls = list(getattr(response, "function_calls", None) or [])
            if not function_calls:
                final_text = getattr(response, "text", "") or ""
                break

            # Record the model's function-call turn.
            contents.append(
                types.Content(
                    role="model",
                    parts=[
                        types.Part(function_call=types.FunctionCall(name=fc.name, args=dict(fc.args or {})))
                        for fc in function_calls
                    ],
                )
            )
            response_parts = []
            for fc in function_calls:
                args = dict(fc.args or {})
                try:
                    tool_result = await executor(fc.name, args)
                except Exception as exc:  # degrade, do not crash the loop
                    tool_result = {"status": "error", "error": str(exc)[:300]}
                steps.append(ToolLoopStep(tool_name=fc.name, args=args, result=tool_result))
                response_parts.append(
                    types.Part.from_function_response(name=fc.name, response={"result": tool_result})
                )
            contents.append(types.Content(role="user", parts=response_parts))

        return ToolLoopResult(text=final_text, steps=steps, iterations=iteration)
