"""FRED (Federal Reserve Economic Data) adapter — multi-series.

API docs: https://fred.stlouisfed.org/docs/api/fred/

Series we treat as discrete events (each new release → one RawEvent):
- CPIAUCSL  Consumer Price Index for All Urban Consumers (monthly)
- PAYEMS    Total Nonfarm Payrolls / NFP (monthly)
- GDPC1     Real Gross Domestic Product (quarterly)

Daily numeric series (10Y / 2Y yields) live in adapters/indicators_fred.py — they
re-use the `_fetch_series_observations` helper here.

Release-date anchoring (the load-bearing subtlety):
  A FRED observation's `date` is the REFERENCE PERIOD (May CPI → "2026-05-01"),
  not the day the number hit the wires (mid-June). Anchoring published_at on
  the reference period made every downstream market-reaction window measure
  the wrong days. We therefore query in ALFRED (vintage) mode — passing a
  realtime range makes the API return one row per (observation, vintage), and
  the FIRST vintage's `realtime_start` is the actual initial release date.
  published_at = release date @ 08:30 ET (CPI / NFP / GDP all print at 8:30).

Derived metrics (what the market actually trades on):
  The raw index level is uninformative to the analyzer LLM. From the
  first-release vintage values we derive the headline numbers — CPI MoM/YoY,
  NFP monthly change in thousands, GDP QoQ annualized — and put them in the
  payload so the prompt can show "CPI MoM +0.4% (prev +0.2%)" instead of
  "index=320.321".

Pure adapter: returns list[RawEvent], performs no DB writes. The Celery task
hands the result to event_writer.persist() which deduplicates and inserts.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

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

# CPI / NFP / GDP all release at 08:30 ET. FRED only gives us the date, so we
# pin the intraday anchor ourselves — it makes the validator's baseline price
# the prior close and the 24h end price the post-release close, which is the
# event-study window we actually want.
_RELEASE_TIME_ET = time(8, 30)
_EASTERN = ZoneInfo("America/New_York")

# How many reference periods (months/quarters) of history we emit as events
# and use for derived-metric computation. 14 months covers YoY + a buffer.
_MAX_PERIODS = 14

# Vintage query lookback: how far back of reference periods to request.
# ~16 months of monthly data with a few revision vintages each stays well
# under the API's row limits.
_OBSERVATION_LOOKBACK_DAYS = 500


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
    """Fetch the most recent N observations for a FRED series (latest vintage).

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


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_series_vintages(series_id: str) -> list[dict[str, Any]]:
    """Fetch observations in ALFRED (vintage) mode.

    Passing a realtime range makes FRED return one row per (observation date,
    vintage); each row's realtime_start says when that value became public.
    The first vintage per observation date = the original release.
    """
    settings = get_settings()
    if not settings.fred_api_key:
        raise RuntimeError("FRED_API_KEY not configured")

    observation_start = (
        datetime.now(UTC) - timedelta(days=_OBSERVATION_LOOKBACK_DAYS)
    ).date()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{FRED_API_BASE}/series/observations",
            params={
                "series_id": series_id,
                "api_key": settings.fred_api_key,
                "file_type": "json",
                "observation_start": observation_start.isoformat(),
                "realtime_start": observation_start.isoformat(),
                "realtime_end": "9999-12-31",
                "sort_order": "asc",
            },
        )
        response.raise_for_status()
        observations: list[dict[str, Any]] = response.json().get("observations", [])
        return observations


@dataclass(frozen=True, slots=True)
class FirstRelease:
    """One reference period's initially-published value + when it was published."""

    reference_period: str  # observation date, 'YYYY-MM-DD'
    release_date: str  # realtime_start of the first vintage, 'YYYY-MM-DD'
    value: float


def _first_releases(vintage_rows: list[dict[str, Any]]) -> list[FirstRelease]:
    """Collapse vintage rows to one FirstRelease per reference period.

    For each observation date keep the vintage with the earliest
    realtime_start — that's the number the market saw on release day.
    Sorted oldest → newest reference period.
    """
    best: dict[str, tuple[str, float]] = {}  # ref_period -> (release_date, value)
    for obs in vintage_rows:
        if obs.get("value") == ".":  # FRED's missing-data marker
            continue
        try:
            value = float(obs["value"])
        except (TypeError, ValueError):
            continue
        ref = obs["date"]
        rt_start = obs.get("realtime_start", "")
        if not rt_start:
            continue
        if ref not in best or rt_start < best[ref][0]:
            best[ref] = (rt_start, value)

    releases = [
        FirstRelease(reference_period=ref, release_date=rd, value=v)
        for ref, (rd, v) in best.items()
    ]
    releases.sort(key=lambda r: r.reference_period)
    return releases


def _derived_metrics(
    spec: FredSeriesSpec, releases: list[FirstRelease], index: int
) -> dict[str, Any]:
    """Headline numbers for releases[index], from first-release values.

    Computed on first-release vintages — the figures the market actually
    reacted to, not later revisions.
    """
    current = releases[index]
    prev = releases[index - 1] if index >= 1 else None
    year_ago = releases[index - 12] if index >= 12 else None

    derived: dict[str, Any] = {}
    if spec.event_type == "CPI_RELEASE":
        if prev and prev.value > 0:
            derived["mom_pct"] = round((current.value / prev.value - 1) * 100, 2)
        if index >= 2 and releases[index - 2].value > 0 and prev:
            derived["prev_mom_pct"] = round(
                (prev.value / releases[index - 2].value - 1) * 100, 2
            )
        if year_ago and year_ago.value > 0:
            derived["yoy_pct"] = round((current.value / year_ago.value - 1) * 100, 2)
    elif spec.event_type == "NFP_RELEASE":
        # PAYEMS is the payrolls LEVEL in thousands; the headline is the change.
        if prev:
            derived["change_thousands"] = round(current.value - prev.value, 1)
        if index >= 2 and prev:
            derived["prev_change_thousands"] = round(
                prev.value - releases[index - 2].value, 1
            )
    elif spec.event_type == "GDP_RELEASE":
        # GDPC1 is the SAAR level; the headline is QoQ annualized growth.
        if prev and prev.value > 0:
            derived["qoq_annualized_pct"] = round(
                ((current.value / prev.value) ** 4 - 1) * 100, 2
            )
        if index >= 2 and prev and releases[index - 2].value > 0:
            derived["prev_qoq_annualized_pct"] = round(
                ((prev.value / releases[index - 2].value) ** 4 - 1) * 100, 2
            )
    return derived


def _headline_str(spec: FredSeriesSpec, derived: dict[str, Any]) -> str:
    """Compact human-readable headline for titles / prompt highlights."""
    if spec.event_type == "CPI_RELEASE":
        parts = []
        if "mom_pct" in derived:
            parts.append(f"MoM {derived['mom_pct']:+.2f}%")
        if "yoy_pct" in derived:
            parts.append(f"YoY {derived['yoy_pct']:+.2f}%")
        return ", ".join(parts)
    if spec.event_type == "NFP_RELEASE":
        if "change_thousands" in derived:
            return f"payrolls {derived['change_thousands']:+,.0f}K"
        return ""
    if spec.event_type == "GDP_RELEASE":
        if "qoq_annualized_pct" in derived:
            return f"QoQ ann. {derived['qoq_annualized_pct']:+.2f}%"
        return ""
    return ""


def _published_at_utc(release_date: str) -> datetime:
    """Release date string → timezone-aware UTC datetime at 08:30 ET."""
    d = date.fromisoformat(release_date)
    local = datetime.combine(d, _RELEASE_TIME_ET, tzinfo=_EASTERN)
    return local.astimezone(UTC)


def _releases_to_raw_events(
    spec: FredSeriesSpec, releases: list[FirstRelease]
) -> list[RawEvent]:
    """Convert first-releases to RawEvents (most recent _MAX_PERIODS only)."""
    events: list[RawEvent] = []
    start = max(0, len(releases) - _MAX_PERIODS)
    for i in range(start, len(releases)):
        rel = releases[i]
        derived = _derived_metrics(spec, releases, i)
        headline = _headline_str(spec, derived)
        title = (
            f"{spec.series_name} for {rel.reference_period} "
            f"released {rel.release_date}: {rel.value}"
        )
        if headline:
            title += f" ({headline})"
        events.append(
            RawEvent(
                source=EventSource.FRED,
                event_type=spec.event_type,
                # Keyed on the reference period — re-fetches and later
                # vintages (revisions) dedupe against the same event.
                external_id=f"{spec.series_id}:{rel.reference_period}",
                title=title[:500],
                payload={
                    "series_id": spec.series_id,
                    "series_name": spec.series_name,
                    "value": rel.value,
                    "reference_period": rel.reference_period,
                    "release_date": rel.release_date,
                    "derived": derived,
                    "headline": headline,
                },
                affected_tickers=list(spec.affected_tickers),
                published_at=_published_at_utc(rel.release_date),
            )
        )
    return events


async def fetch_new() -> list[RawEvent]:
    """Pull vintage history for every event-series and return them as RawEvents."""
    log = logger.bind(source="FRED", series_count=len(FRED_EVENT_SERIES))
    log.info("fred.fetch.started")

    events: list[RawEvent] = []
    for spec in FRED_EVENT_SERIES:
        vintage_rows = await _fetch_series_vintages(spec.series_id)
        releases = _first_releases(vintage_rows)
        events.extend(_releases_to_raw_events(spec, releases))

    log.info("fred.fetch.completed", parsed=len(events))
    return events
