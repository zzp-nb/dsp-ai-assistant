"""Model price configuration and cost estimation (currency: CNY)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelPrice:
    cache_hit_per_million: float
    cache_miss_per_million: float
    output_per_million: float


@dataclass(frozen=True)
class CostEstimate:
    cny: float
    known_price: bool
    price_version: str


class CostTracker:
    def __init__(self, pricing: dict[str, Any]):
        self.pricing = pricing
        self.version = str(pricing.get("version", "unknown"))
        self.currency = str(pricing.get("currency", "CNY"))

    def price_for(self, model: str) -> ModelPrice | None:
        models = self.pricing.get("models", {})
        item = models.get(model) if isinstance(models, dict) else None
        if not isinstance(item, dict):
            return None
        try:
            return ModelPrice(
                cache_hit_per_million=float(item.get("input_cache_hit_cny_per_million", 0)),
                cache_miss_per_million=float(item.get("input_cache_miss_cny_per_million", 0)),
                output_per_million=float(item.get("output_cny_per_million", 0)),
            )
        except (TypeError, ValueError):
            return None

    def estimate(
        self,
        model: str,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        cache_hit_tokens: int = 0,
        cache_miss_tokens: int | None = None,
    ) -> CostEstimate:
        price = self.price_for(model)
        if price is None:
            return CostEstimate(0.0, False, self.version)
        hit = max(0, min(int(cache_hit_tokens), int(prompt_tokens)))
        miss = (
            max(0, int(prompt_tokens) - hit)
            if cache_miss_tokens is None
            else max(0, int(cache_miss_tokens))
        )
        # If only total prompt tokens are known, charge the conservative miss price.
        if hit == 0 and cache_miss_tokens is None:
            miss = int(prompt_tokens)
        cost = (
            hit / 1_000_000 * price.cache_hit_per_million
            + miss / 1_000_000 * price.cache_miss_per_million
            + max(0, int(completion_tokens)) / 1_000_000 * price.output_per_million
        )
        return CostEstimate(round(cost, 6), True, self.version)


def format_cny(amount: float) -> str:
    if amount < 0.01:
        return f"¥{amount:.4f}"
    return f"¥{amount:.2f}"
