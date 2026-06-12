from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True)
class LLMCostSummary:
    month: str
    estimated_cost_usd: float
    monthly_budget_usd: float
    budget_exceeded: bool
    tracking_available: bool = True

    def as_dict(self) -> dict:
        return {
            "month": self.month,
            "estimated_cost_usd": self.estimated_cost_usd,
            "monthly_budget_usd": self.monthly_budget_usd,
            "budget_exceeded": self.budget_exceeded,
            "tracking_available": self.tracking_available,
        }


class CostTracker(Protocol):
    monthly_budget_usd: float

    def add_estimated_cost(self, month: str, amount_usd: float) -> None:
        ...

    def get_summary(self, month: str) -> dict:
        ...


def current_month_key(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.strftime("%Y-%m")


def estimate_cost_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    input_price_per_million: float,
    output_price_per_million: float,
) -> float:
    return (input_tokens / 1_000_000 * input_price_per_million) + (
        output_tokens / 1_000_000 * output_price_per_million
    )


class InMemoryCostTracker:
    def __init__(self, *, monthly_budget_usd: float) -> None:
        self.monthly_budget_usd = monthly_budget_usd
        self._costs: dict[str, float] = {}

    def add_estimated_cost(self, month: str, amount_usd: float) -> None:
        self._costs[month] = self._costs.get(month, 0.0) + amount_usd

    def get_summary(self, month: str) -> dict:
        total = round(self._costs.get(month, 0.0), 6)
        return LLMCostSummary(
            month=month,
            estimated_cost_usd=total,
            monthly_budget_usd=self.monthly_budget_usd,
            budget_exceeded=total >= self.monthly_budget_usd,
        ).as_dict()


class RedisCostTracker:
    def __init__(
        self,
        *,
        redis_url: str,
        monthly_budget_usd: float,
        key_prefix: str = "agent:llm:cost",
    ) -> None:
        self.monthly_budget_usd = monthly_budget_usd
        self.key_prefix = key_prefix
        from redis import Redis

        self.client = Redis.from_url(
            redis_url,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
            decode_responses=True,
        )

    def _key(self, month: str) -> str:
        return f"{self.key_prefix}:{month}"

    def add_estimated_cost(self, month: str, amount_usd: float) -> None:
        self.client.incrbyfloat(self._key(month), amount_usd)

    def get_summary(self, month: str) -> dict:
        raw = self.client.get(self._key(month))
        total = round(float(raw or 0.0), 6)
        return LLMCostSummary(
            month=month,
            estimated_cost_usd=total,
            monthly_budget_usd=self.monthly_budget_usd,
            budget_exceeded=total >= self.monthly_budget_usd,
        ).as_dict()


def unavailable_cost_summary(
    *,
    month: str,
    monthly_budget_usd: float,
) -> dict:
    return LLMCostSummary(
        month=month,
        estimated_cost_usd=0.0,
        monthly_budget_usd=monthly_budget_usd,
        budget_exceeded=False,
        tracking_available=False,
    ).as_dict()


def get_runtime_cost_summary(settings) -> dict:
    month = current_month_key()
    if not settings.AGENT_LLM_COST_TRACKING_ENABLED:
        return unavailable_cost_summary(
            month=month,
            monthly_budget_usd=settings.AGENT_LLM_MONTHLY_BUDGET_USD,
        )
    try:
        tracker = RedisCostTracker(
            redis_url=settings.REDIS_URL,
            monthly_budget_usd=settings.AGENT_LLM_MONTHLY_BUDGET_USD,
        )
        return tracker.get_summary(month)
    except Exception:
        return unavailable_cost_summary(
            month=month,
            monthly_budget_usd=settings.AGENT_LLM_MONTHLY_BUDGET_USD,
        )
