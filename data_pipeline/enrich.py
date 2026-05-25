from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable

import httpx


@dataclass
class NominatimGeocoder:
    user_agent: str
    rate_limit_seconds: float = 1.0
    base_url: str = "https://nominatim.openstreetmap.org/search"
    client_factory: Callable[[], object] = field(default=lambda: httpx.AsyncClient(timeout=15))

    async def geocode(self, address: str) -> tuple[float, float] | None:
        if not address or not address.strip():
            return None

        async with self.client_factory() as client:
            response = await client.get(
                self.base_url,
                params={"q": address.strip(), "format": "json", "limit": 1},
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()
            data = response.json()

        if self.rate_limit_seconds > 0:
            await asyncio.sleep(self.rate_limit_seconds)

        if not data:
            return None

        try:
            return float(data[0]["lat"]), float(data[0]["lon"])
        except (KeyError, ValueError):
            return None
