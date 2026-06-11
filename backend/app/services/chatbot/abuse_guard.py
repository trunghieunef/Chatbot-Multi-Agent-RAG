"""Lightweight in-memory chat abuse guard."""

from collections import defaultdict, deque
from dataclasses import dataclass
from math import ceil
from time import monotonic

from fastapi import HTTPException, Response


@dataclass(frozen=True)
class AbuseGuardResult:
    allowed: bool
    retry_after_seconds: int = 0


class ChatAbuseGuard:
    """Sliding-window request counter keyed by caller identity."""

    def __init__(self, max_requests: int, window_seconds: int, clock=monotonic):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._requests = defaultdict(deque)

    def check(self, key: str) -> AbuseGuardResult:
        now = self._clock()
        window_start = now - self.window_seconds
        timestamps = self._requests[key]

        while timestamps and timestamps[0] <= window_start:
            timestamps.popleft()

        if len(timestamps) >= self.max_requests:
            retry_after = max(1, ceil(timestamps[0] + self.window_seconds - now))
            return AbuseGuardResult(
                allowed=False,
                retry_after_seconds=retry_after,
            )

        timestamps.append(now)
        return AbuseGuardResult(allowed=True)


def enforce_chat_abuse_guard(
    guard: ChatAbuseGuard,
    *,
    key: str,
    enabled: bool,
    response: Response,
) -> None:
    if not enabled:
        return

    result = guard.check(key)
    if result.allowed:
        return

    retry_after = str(result.retry_after_seconds)
    response.headers["Retry-After"] = retry_after
    raise HTTPException(
        status_code=429,
        detail="He thong dang nhan qua nhieu yeu cau. Vui long thu lai sau.",
        headers={"Retry-After": retry_after},
    )
