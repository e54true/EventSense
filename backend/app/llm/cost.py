"""LLM pricing + daily-spend guardrail.

Pricing table is hardcoded — updates are infrequent (model pricing changes
maybe once a year). When prices move, bump the constants and ship.

The daily cap check queries SUM(llm_cost_usd) for today's predictions; if
above the configured cap, the router downgrades premium calls to the default
(cheaper) model. We log a warning but don't block analysis entirely — better
to keep producing predictions on the cheap model than to go silent.
"""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Prediction

logger = structlog.get_logger(__name__)

# USD per 1M tokens. Updated 2026-05. Source: openai.com/pricing, anthropic.com/pricing.
# Keep keys lowercase for case-insensitive lookup.
_PRICING_USD_PER_M_TOKENS: dict[str, tuple[float, float]] = {
    # (input_price, output_price)
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-2024-08-06": (2.50, 10.00),
    "claude-3-5-haiku-latest": (0.80, 4.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-sonnet-4-5-20250929": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Convert a usage triple into USD cost. Unknown models cost 0 (safe default
    for tests / models we forgot to add to the pricing table)."""
    pricing = _PRICING_USD_PER_M_TOKENS.get(model.lower())
    if pricing is None:
        logger.warning("cost.unknown_model", model=model)
        return 0.0
    input_price, output_price = pricing
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000


async def today_spend_usd(db: AsyncSession) -> float:
    """SUM of llm_cost_usd across predictions emitted since UTC midnight today.

    UTC chosen over local time so deployments in different timezones agree on
    where the day boundary is.
    """
    start_of_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.scalar(
        select(func.coalesce(func.sum(Prediction.llm_cost_usd), 0.0)).where(
            Prediction.predicted_at >= start_of_day
        )
    )
    return float(result or 0.0)


def time_until_next_midnight_utc() -> timedelta:
    """How long until the spend counter resets — useful for log messages."""
    now = datetime.now(UTC)
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return tomorrow - now
