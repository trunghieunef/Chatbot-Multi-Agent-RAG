from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from agent_service.config import get_agent_settings


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_agent_settings()
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL

    def generate_text(self, prompt: str) -> str:
        if not self.api_key:
            return ""

        from google import genai

        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(model=self.model, contents=prompt)
        return response.text or ""

    def generate_json(self, prompt: str) -> dict[str, Any]:
        text = self.generate_text(prompt)
        if not text:
            return {}

        try:
            parsed = json.loads(text)
        except JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
