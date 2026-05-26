"""Picks which (provider, model) to use for a given event.

Two axes:
  1. Event "tier": high-stakes events (FOMC, surprise CPI) get the premium model;
     routine 8-Ks get the cheap default model.
  2. Budget: if today's spend already exceeded the daily cap, EVERY call is
     forced down to the default model regardless of tier. We don't go silent —
     a downgraded prediction beats no prediction.

The router stays deliberately simple (hardcoded rules) per spec §9. A more
sophisticated version could route by historical accuracy per source/model, but
that's future work.
"""

from dataclasses import dataclass
from typing import Literal

import structlog

from app.config.settings import get_settings
from app.db.models import EventSource

logger = structlog.get_logger(__name__)

Provider = Literal["openai", "anthropic"]


@dataclass(frozen=True, slots=True)
class ModelChoice:
    provider: Provider
    model: str


# Event types deemed "high-stakes" enough to deserve the premium model.
# Everything else falls through to the default (cheap) model.
_HIGH_STAKES_EVENT_TYPES: frozenset[tuple[EventSource, str]] = frozenset(
    {
        (EventSource.FOMC, "FOMC_STATEMENT"),
        # CPI is the biggest scheduled macro print of each month; LLM nuance
        # on dovish/hawkish language is worth the premium model price.
        (EventSource.FRED, "ECONOMIC_RELEASE"),
    }
)


def _provider_for_model(model: str) -> Provider:
    """Infer provider from model name — keeps router config terse."""
    return "anthropic" if model.lower().startswith("claude") else "openai"


def choose_model(
    source: EventSource,
    event_type: str,
    today_spend_usd: float,
) -> ModelChoice:
    """Decide which model to use for one event.

    `today_spend_usd` is passed in (not queried here) so the router stays sync
    and trivially testable.
    """
    settings = get_settings()

    over_budget = today_spend_usd >= settings.llm_daily_cost_cap_usd
    if over_budget:
        # Hard fallback to default model regardless of event tier.
        logger.warning(
            "router.over_budget",
            spend=today_spend_usd,
            cap=settings.llm_daily_cost_cap_usd,
            downgraded_to=settings.llm_default_model,
        )
        model = settings.llm_default_model
    elif (source, event_type) in _HIGH_STAKES_EVENT_TYPES:
        model = settings.llm_premium_model
    else:
        model = settings.llm_default_model

    return ModelChoice(provider=_provider_for_model(model), model=model)
