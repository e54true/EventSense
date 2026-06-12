"""FRED daily-yield indicator adapter.

Pulls daily Treasury yield observations from FRED and returns them as
IndicatorObservations (NOT RawEvents). The indicators pipeline is independent
of the events FETCHED→ANALYZED state machine — these are *state* that the v2
analyzer reads as context.

Series:
- DGS10  10-Year Treasury Constant Maturity Rate (daily)
- DGS2   2-Year  Treasury Constant Maturity Rate (daily)

We pull the most recent ~60 observations on each poll. The
`uq_indicators_key_observed` unique constraint dedups, so repeated polls are
cheap.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from app.adapters.fred import _fetch_series_observations
from app.schemas.indicator import IndicatorObservation

logger = structlog.get_logger(__name__)

# 60 business-day window — comfortably covers any operational gap between
# polls without burning quota when the daily Beat is reliable.
_OBSERVATION_LIMIT = 60


@dataclass(frozen=True, slots=True)
class FredIndicatorSpec:
    """One FRED series we ingest as a time-series indicator."""

    series_id: str
    indicator_key: str


FRED_INDICATOR_SERIES: list[FredIndicatorSpec] = [
    FredIndicatorSpec(series_id="DGS10", indicator_key="DGS10"),
    FredIndicatorSpec(series_id="DGS2", indicator_key="DGS2"),
]


def _observation_to_indicator(
    obs: dict[str, Any], spec: FredIndicatorSpec
) -> IndicatorObservation | None:
    """Convert one FRED observation to an IndicatorObservation."""
    if obs.get("value") == ".":  # FRED's missing-data marker (holiday, no print)
        return None
    try:
        value = float(obs["value"])
    except (TypeError, ValueError):
        return None

    observed_date = obs["date"]  # 'YYYY-MM-DD'
    return IndicatorObservation(
        indicator_key=spec.indicator_key,
        observed_at=datetime.fromisoformat(observed_date).replace(tzinfo=UTC),
        value=value,
        source="FRED",
        payload={"series_id": spec.series_id, "raw": obs},
    )


async def fetch_new() -> list[IndicatorObservation]:
    """Pull recent observations for every indicator series."""
    log = logger.bind(source="FRED_INDICATORS", series_count=len(FRED_INDICATOR_SERIES))
    log.info("indicators_fred.fetch.started")

    observations: list[IndicatorObservation] = []
    for spec in FRED_INDICATOR_SERIES:
        rows = await _fetch_series_observations(spec.series_id, limit=_OBSERVATION_LIMIT)
        observations.extend(o for row in rows if (o := _observation_to_indicator(row, spec)))

    log.info("indicators_fred.fetch.completed", parsed=len(observations))
    return observations
