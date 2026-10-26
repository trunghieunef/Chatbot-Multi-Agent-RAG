from __future__ import annotations

import os

from fastapi import HTTPException


def require_internal_key(x_internal_agent_key: str | None) -> None:
    expected = os.environ.get("AGENT_INTERNAL_KEY", "")
    if not expected or x_internal_agent_key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal key")
