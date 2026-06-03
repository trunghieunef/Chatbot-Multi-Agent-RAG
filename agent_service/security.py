from fastapi import Header, HTTPException, status

from agent_service.config import get_agent_settings


async def require_internal_key(
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> None:
    settings = get_agent_settings()
    if not x_internal_agent_key or x_internal_agent_key != settings.AGENT_INTERNAL_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal agent key",
        )
