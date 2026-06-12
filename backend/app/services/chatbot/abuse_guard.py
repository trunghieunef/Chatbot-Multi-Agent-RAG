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

    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        clock=monotonic,
        max_keys: int = 10000,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._clock = clock
        self._requests = defaultdict(deque)

    def _prune(self, now: float) -> None:
        window_start = now - self.window_seconds
        empty_keys = []
        for key, timestamps in self._requests.items():
            while timestamps and timestamps[0] <= window_start:
                timestamps.popleft()
            if not timestamps:
                empty_keys.append(key)
        for key in empty_keys:
            self._requests.pop(key, None)

        while len(self._requests) > self.max_keys:
            oldest_key = min(
                self._requests,
                key=lambda key: self._requests[key][0] if self._requests[key] else now,
            )
            self._requests.pop(oldest_key, None)

    def check(self, key: str) -> AbuseGuardResult:
        now = self._clock()
        self._prune(now)
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
        self._prune(now)
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
