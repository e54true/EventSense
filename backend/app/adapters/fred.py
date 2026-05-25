"""FRED (Federal Reserve Economic Data) adapter.

API docs: https://fred.stlouisfed.org/docs/api/fred/

Pure adapter: returns list[RawEvent], performs no DB writes. The Celery task
hands the result to event_writer.persist() which deduplicates and inserts.
"""

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
CPI_SERIES_ID = "CPIAUCSL"


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_series_observations(series_id: str, limit: int = 12) -> list[dict[str, Any]]:
    """Fetch the most recent N observations for a FRED series."""
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
        return response.json().get("observations", [])


def _observation_to_raw_event(obs: dict[str, Any], series_id: str) -> RawEvent | None:
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
        event_type="ECONOMIC_RELEASE",
        external_id=f"{series_id}:{release_date}",
        title=f"CPI release for {release_date}: {value}",
        payload={
            "series_id": series_id,
            "series_name": "Consumer Price Index for All Urban Consumers",
            "value": value,
            "release_date": release_date,
            "raw": obs,
        },
        affected_tickers=[],  # CPI affects market-wide; per-ticker mapping is Analyzer's job
        published_at=datetime.fromisoformat(release_date).replace(tzinfo=UTC),
    )


async def fetch_new() -> list[RawEvent]:
    """Fetch latest CPI observations and return them as RawEvents (no DB writes)."""
    log = logger.bind(source="FRED", series_id=CPI_SERIES_ID)
    log.info("fred.fetch.started")

    observations = await _fetch_series_observations(CPI_SERIES_ID)
    events = [e for obs in observations if (e := _observation_to_raw_event(obs, CPI_SERIES_ID))]

    log.info("fred.fetch.completed", parsed=len(events), total_observations=len(observations))
    return events
