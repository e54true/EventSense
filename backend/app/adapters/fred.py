"""FRED (Federal Reserve Economic Data) adapter.

API docs: https://fred.stlouisfed.org/docs/api/fred/

For Milestone 1 we only fetch CPIAUCSL (Consumer Price Index) as a proof of concept.
Multi-series fetching arrives in Milestone 3.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.models import Event, EventSource, EventStatus

logger = structlog.get_logger(__name__)

FRED_API_BASE = "https://api.stlouisfed.org/fred"

# CPI for All Urban Consumers (released monthly, ~10th-15th of the month)
CPI_SERIES_ID = "CPIAUCSL"


async def _fetch_series_observations(series_id: str, limit: int = 12) -> list[dict[str, Any]]:
    """Fetch the most recent N observations for a FRED series.

    Returns list of {date: 'YYYY-MM-DD', value: 'N.N'} dicts, sorted by date descending.
    Sort order is set explicitly because FRED's default differs by series.
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
        return response.json().get("observations", [])


async def fetch_cpi(db: AsyncSession) -> int:
    """Fetch latest CPI observations and insert any new ones into events table.

    Returns the count of newly inserted events (0 if no new observations since last poll).
    Idempotent: relies on (source, external_id) unique constraint to dedup.
    """
    log = logger.bind(source="FRED", series_id=CPI_SERIES_ID)
    log.info("fred.fetch.started")

    try:
        observations = await _fetch_series_observations(CPI_SERIES_ID)
    except httpx.HTTPError as exc:
        log.error("fred.fetch.http_error", error=str(exc))
        raise

    inserted = 0
    for obs in observations:
        # FRED uses "." to indicate missing data
        if obs.get("value") == ".":
            continue

        release_date = obs["date"]  # 'YYYY-MM-DD' string
        external_id = f"{CPI_SERIES_ID}:{release_date}"

        # Quick existence check to avoid unnecessary INSERT attempts.
        # The unique constraint is still the source of truth — this is a perf optimization.
        existing = await db.scalar(
            select(Event.id).where(
                Event.source == EventSource.FRED,
                Event.external_id == external_id,
            )
        )
        if existing is not None:
            continue

        try:
            value = float(obs["value"])
        except (TypeError, ValueError):
            log.warning("fred.fetch.skip_bad_value", obs=obs)
            continue

        published_at = datetime.fromisoformat(release_date).replace(tzinfo=UTC)
        now = datetime.now(UTC)

        event = Event(
            source=EventSource.FRED,
            event_type="ECONOMIC_RELEASE",
            external_id=external_id,
            title=f"CPI release for {release_date}: {value}",
            payload={
                "series_id": CPI_SERIES_ID,
                "series_name": "Consumer Price Index for All Urban Consumers",
                "value": value,
                "release_date": release_date,
                "raw": obs,
            },
            affected_tickers=[],  # CPI affects everything; per-ticker mapping deferred to Analyzer
            published_at=published_at,
            fetched_at=now,
            status=EventStatus.FETCHED,
        )
        db.add(event)
        try:
            await db.flush()
        except IntegrityError:
            # Race condition: another worker inserted the same row between our SELECT and flush.
            # Roll back this row and continue — the (source, external_id) unique constraint did its job.
            await db.rollback()
            continue
        inserted += 1

    await db.commit()
    log.info("fred.fetch.completed", inserted=inserted, total_observations=len(observations))
    return inserted
