from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from app.config import get_settings
from app.services.agent_service.contracts import AgentChatRequest, AgentChatResponse


TRANSIENT_ERRORS = (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError)


class AgentServiceError(RuntimeError):
    """Raised when the internal Agent Service cannot return a valid response."""

    def __init__(self, message: str, *, error_type: str = "unknown") -> None:
        super().__init__(message)
        self.error_type = error_type


class AgentServiceClient:
    def __init__(
        self,
        *,
        base_url: str,
        internal_key: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.internal_key = internal_key
        self.timeout_seconds = timeout_seconds
        self.transport = transport


    async def chat(self, body: AgentChatRequest) -> AgentChatResponse:
        return await self._chat_endpoint(body, "/internal/agent/chat")

    async def chat_stream(self, body: AgentChatRequest) -> AsyncIterator[dict]:
        """Call Agent Service streaming endpoint, yield parsed SSE events.

        Each yielded dict has: {event, node?, status?, duration_ms?, payload?}
        Final event: {event: "final", request_id, payload: AgentChatResponse}
        """
        headers = {
            "X-Internal-Agent-Key": self.internal_key,
            "Accept": "text/event-stream",
        }
        timeout = httpx.Timeout(self.timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self.transport,
            ) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/internal/agent/chat/stream",
                    json=body.model_dump(mode="json"),
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            try:
                                yield json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
        except httpx.HTTPStatusError as exc:
            yield {
                "event": "error",
                "request_id": body.request_id,
                "payload": {
                    "code": "agent_stream_error",
                    "message": f"Agent Service stream failed: HTTP {exc.response.status_code}",
                },
            }
        except httpx.HTTPError as exc:
            yield {
                "event": "error",
                "request_id": body.request_id,
                "payload": {
                    "code": "agent_stream_network",
                    "message": f"Agent Service stream failed: {exc.__class__.__name__}",
                },
            }

    async def chat_v2(self, body: AgentChatRequest) -> AgentChatResponse:
        """Call the Agentic RAG endpoint (autonomous agents + LLM thinking)."""
        return await self._chat_endpoint(body, "/internal/agent/chat-v2")

    async def _chat_endpoint(self, body: AgentChatRequest, path: str) -> AgentChatResponse:
        headers = {"X-Internal-Agent-Key": self.internal_key}
        timeout = httpx.Timeout(self.timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self.transport,
            ) as client:
                try:
                    response = await client.post(
                        f"{self.base_url}{path}",
                        json=body.model_dump(mode="json"),
                        headers=headers,
                    )
                except TRANSIENT_ERRORS:
                    response = await client.post(
                        f"{self.base_url}{path}",
                        json=body.model_dump(mode="json"),
                        headers=headers,
                    )
                response.raise_for_status()
                return AgentChatResponse.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise AgentServiceError(
                f"Agent Service request failed: HTTP {status_code}",
                error_type="http_status",
            ) from None
        except httpx.HTTPError as exc:
            error_type = exc.__class__.__name__
            safe_type = (
                "transient_network"
                if isinstance(exc, TRANSIENT_ERRORS)
                else "network"
            )
            raise AgentServiceError(
                f"Agent Service request failed: {error_type}",
                error_type=safe_type,
            ) from None
        except ValueError as exc:
            raise AgentServiceError(
                "Agent Service request failed: invalid response",
                error_type="invalid_response",
            ) from None

    async def evaluate(self, body: dict) -> dict:
        headers = {"X-Internal-Agent-Key": self.internal_key}
        timeout = httpx.Timeout(self.timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/internal/agent/evaluate",
                    json=body,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("invalid response")
                return data
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise AgentServiceError(
                f"Agent Service request failed: HTTP {status_code}",
                error_type="http_status",
            ) from None
        except httpx.HTTPError as exc:
            error_type = exc.__class__.__name__
            raise AgentServiceError(
                f"Agent Service request failed: {error_type}",
                error_type="network",
            ) from None
        except ValueError as exc:
            raise AgentServiceError(
                "Agent Service request failed: invalid response",
                error_type="invalid_response",
            ) from None

    async def health(self) -> dict:
        headers = {"X-Internal-Agent-Key": self.internal_key}
        timeout = httpx.Timeout(self.timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self.transport,
            ) as client:
                response = await client.get(
                    f"{self.base_url}/internal/agent/health",
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("invalid response")
                return data
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise AgentServiceError(
                f"Agent Service request failed: HTTP {status_code}",
                error_type="http_status",
            ) from None
        except httpx.HTTPError as exc:
            error_type = exc.__class__.__name__
            raise AgentServiceError(
                f"Agent Service request failed: {error_type}",
                error_type="network",
            ) from None
        except ValueError:
            raise AgentServiceError(
                "Agent Service request failed: invalid response",
                error_type="invalid_response",
            ) from None


def get_agent_service_client() -> AgentServiceClient:
    settings = get_settings()
    return AgentServiceClient(
        base_url=settings.AGENT_SERVICE_URL,
        internal_key=settings.AGENT_INTERNAL_KEY,
        timeout_seconds=settings.AGENT_SERVICE_TIMEOUT_SECONDS,
    )
