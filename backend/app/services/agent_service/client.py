from __future__ import annotations

import httpx

from app.config import get_settings
from app.services.agent_service.contracts import AgentChatRequest, AgentChatResponse


class AgentServiceError(RuntimeError):
    """Raised when the internal Agent Service cannot return a valid response."""


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
        headers = {"X-Internal-Agent-Key": self.internal_key}
        timeout = httpx.Timeout(self.timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/internal/agent/chat",
                    json=body.model_dump(mode="json"),
                    headers=headers,
                )
                response.raise_for_status()
                return AgentChatResponse.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise AgentServiceError(
                f"Agent Service request failed: HTTP {status_code}"
            ) from None
        except httpx.HTTPError as exc:
            error_type = exc.__class__.__name__
            raise AgentServiceError(
                f"Agent Service request failed: {error_type}"
            ) from None
        except ValueError as exc:
            raise AgentServiceError(
                "Agent Service request failed: invalid response"
            ) from None


def get_agent_service_client() -> AgentServiceClient:
    settings = get_settings()
    return AgentServiceClient(
        base_url=settings.AGENT_SERVICE_URL,
        internal_key=settings.AGENT_INTERNAL_KEY,
        timeout_seconds=settings.AGENT_SERVICE_TIMEOUT_SECONDS,
    )
