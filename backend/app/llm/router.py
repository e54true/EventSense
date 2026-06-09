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
        (EventSource.FOMC, "DOT_PLOT_RELEASE"),  # SEP — quarterly forward guidance signal
        # Macro prints that move the whole curve and SPY. LLM nuance on the
        # dovish/hawkish lean of each release is worth the premium model price.
        (EventSource.FRED, "CPI_RELEASE"),
        (EventSource.FRED, "NFP_RELEASE"),
        (EventSource.FRED, "GDP_RELEASE"),
        # Back-compat: legacy rows from before the multi-series rename. The
        # Phase 1 migration backfills them to CPI_RELEASE but keep the alias
        # in case of a rolling deploy ordering quirk.
        (EventSource.FRED, "ECONOMIC_RELEASE"),
        # Earnings ships with rich payload (Phase A fundamentals + SEC linkage
        # + EX-99.1 press release via attached docs). gpt-4o-mini routinely
        # ignored the v3.2 prompt's "MUST anchor to historical period"
        # requirement; gpt-4o reliably follows that structure. ~7 earnings/
        # quarter x 4 quarters/yr x $0.03/call ~ $1/year — easy upgrade.
        (EventSource.EARNINGS, "EARNINGS_REPORT"),
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
