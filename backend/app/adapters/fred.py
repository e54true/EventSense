"""FRED (Federal Reserve Economic Data) adapter — multi-series.

API docs: https://fred.stlouisfed.org/docs/api/fred/

Series we treat as discrete events (each new release → one RawEvent):
- CPIAUCSL  Consumer Price Index for All Urban Consumers (monthly)
- PAYEMS    Total Nonfarm Payrolls / NFP (monthly)
- GDPC1     Real Gross Domestic Product (quarterly)

Daily numeric series (10Y / 2Y yields) live in adapters/indicators_fred.py — they
re-use the `_fetch_series_observations` helper here.

Pure adapter: returns list[RawEvent], performs no DB writes. The Celery task
hands the result to event_writer.persist() which deduplicates and inserts.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config.settings import get_settings
from app.db.models import EventSource
from app.schemas.raw_event import RawEvent

logger = structlog.get_logger(__name__)

FRED_API_BASE = "https://api.stlouisfed.org/fred"


@dataclass(frozen=True, slots=True)
class FredSeriesSpec:
    """One FRED series we ingest as discrete events.

    `event_type` is the column value in the events table (CPI_RELEASE etc).
    `series_name` lands in payload for prompt readability.
    """

    series_id: str
    series_name: str
    event_type: str
    # Empty for macro series — the Analyzer decides per-ticker impact.
    affected_tickers: list[str] = field(default_factory=list)


FRED_EVENT_SERIES: list[FredSeriesSpec] = [
    FredSeriesSpec(
        series_id="CPIAUCSL",
        series_name="Consumer Price Index for All Urban Consumers",
        event_type="CPI_RELEASE",
    ),
    FredSeriesSpec(
        series_id="PAYEMS",
        series_name="All Employees, Total Nonfarm (NFP)",
        event_type="NFP_RELEASE",
    ),
    FredSeriesSpec(
        series_id="GDPC1",
        series_name="Real Gross Domestic Product",
        event_type="GDP_RELEASE",
    ),
]


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_series_observations(series_id: str, limit: int = 12) -> list[dict[str, Any]]:
    """Fetch the most recent N observations for a FRED series.

    Shared with adapters/indicators_fred.py — keep the signature stable.
    """
    settings = get_settings()
    if not settings.fred_api_key:
        raise RuntimeError("FRED_API_KEY not configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{FRED_API_BASE}/series/observations",
            params={
                "series_id": series_id,
                "api_key": settings.fred_api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
        )
        response.raise_for_status()
        observations: list[dict[str, Any]] = response.json().get("observations", [])
        return observations


def _observation_to_raw_event(
    obs: dict[str, Any], spec: FredSeriesSpec
) -> RawEvent | None:
    """Convert one FRED observation to a RawEvent. None if the row is missing/invalid."""
    if obs.get("value") == ".":  # FRED's missing-data marker
        return None

    try:
        value = float(obs["value"])
    except (TypeError, ValueError):
        return None

    release_date = obs["date"]  # 'YYYY-MM-DD'
    return RawEvent(
        source=EventSource.FRED,
        event_type=spec.event_type,
        external_id=f"{spec.series_id}:{release_date}",
        title=f"{spec.series_name} release for {release_date}: {value}",
        payload={
            "series_id": spec.series_id,
            "series_name": spec.series_name,
            "value": value,
            "release_date": release_date,
            "raw": obs,
        },
        affected_tickers=list(spec.affected_tickers),
        published_at=datetime.fromisoformat(release_date).replace(tzinfo=UTC),
    )


async def fetch_new() -> list[RawEvent]:
    """Pull latest observations for every event-series and return them as RawEvents."""
    log = logger.bind(source="FRED", series_count=len(FRED_EVENT_SERIES))
    log.info("fred.fetch.started")

    events: list[RawEvent] = []
    for spec in FRED_EVENT_SERIES:
        observations = await _fetch_series_observations(spec.series_id)
        events.extend(
            e for obs in observations if (e := _observation_to_raw_event(obs, spec))
        )

    log.info("fred.fetch.completed", parsed=len(events))
    return events
