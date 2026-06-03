from secrets import compare_digest

from fastapi import Header, HTTPException, status

from agent_service.config import get_agent_settings

DEV_AGENT_INTERNAL_KEY = "dev-agent-internal-key"


async def require_internal_key(
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> None:
    settings = get_agent_settings()
    if not settings.DEBUG and settings.AGENT_INTERNAL_KEY == DEV_AGENT_INTERNAL_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent internal key is not configured securely",
        )
    if not x_internal_agent_key or not compare_digest(
        x_internal_agent_key, settings.AGENT_INTERNAL_KEY
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal agent key",
        )
