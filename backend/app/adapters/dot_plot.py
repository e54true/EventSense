"""FOMC Summary of Economic Projections (SEP) — "dot plot" adapter.

The SEP is the Fed's quarterly projection set, released alongside the
FOMC statement four times a year. The headline data point for markets is the
**federal funds rate projection** — median and range across the 19 participants
for the next 3 years + longer run. We parse the published HTML table and emit
one RawEvent per release.

Source URLs:
- Calendar index: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- Per-release:    https://www.federalreserve.gov/monetarypolicy/fomcprojtabl{YYYYMMDD}.htm

The YYYYMMDD in the URL is the FOMC meeting date — natural primary key.

We poll the calendar page weekly (rare event, no urgency); the (source,
external_id) unique constraint dedups everything older.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from bs4 import BeautifulSoup

from app.db.models import EventSource
from app.schemas.raw_event import RawEvent

logger = structlog.get_logger(__name__)

CALENDARS_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
_PROJ_URL_TMPL = "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl{ymd}.htm"
_USER_AGENT = "EventSense/0.1 dev@example.com"
_REQUEST_TIMEOUT_SEC = 20.0

# How many recent SEP releases to ingest on each poll. 8 ≈ 2 years of history;
# all but the newest are de-duped by the unique constraint.
_INGEST_RECENT_N = 8

_PROJ_LINK_PATTERN = re.compile(r"fomcprojtabl(\d{8})\.htm")


async def _fetch_html(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT_SEC,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except Exception as exc:
        logger.warning("dot_plot.fetch.failed", url=url, error=str(exc))
        return None


def _extract_release_dates(calendars_html: str) -> list[str]:
    """Return YYYYMMDD strings for SEP releases, sorted newest-first."""
    matches = _PROJ_LINK_PATTERN.findall(calendars_html)
    # Unique, newest-first; we want lexicographic descending which matches
    # chronological for YYYYMMDD format.
    return sorted(set(matches), reverse=True)


def _parse_year_header(rows: list[Any]) -> list[str]:
    """The second row of the projections table lists the year columns thrice
    (Median | Central Tendency | Range). We just need the first 4 unique year
    labels (e.g. ['2026','2027','2028','Longer run'])."""
    if len(rows) < 2:
        return []
    cells = [c.get_text(strip=True) for c in rows[1].find_all(["th", "td"])]
    # Take the first 4 — same set repeats under each of the 3 statistic columns.
    seen: list[str] = []
    for c in cells:
        if c and c not in seen:
            seen.append(c)
        if len(seen) == 4:
            break
    return seen


def _parse_projection_table(html: str) -> dict[str, Any] | None:
    """Extract median / central tendency / range of the federal funds rate from
    the first projections table on a SEP page."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            year_labels = _parse_year_header(rows)
            if not year_labels:
                continue
            for row in rows:
                cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
                if not cells:
                    continue
                if cells[0].lower().startswith("federal funds"):
                    # 1 variable + 4 median + 4 central_tendency + 4 range = 13 cells
                    if len(cells) < 13:
                        return None
                    return {
                        "median": dict(zip(year_labels, cells[1:5], strict=True)),
                        "central_tendency": dict(
                            zip(year_labels, cells[5:9], strict=True)
                        ),
                        "range": dict(zip(year_labels, cells[9:13], strict=True)),
                    }
        return None
    except Exception as exc:
        logger.warning("dot_plot.parse.failed", error=str(exc))
        return None


def _to_raw_event(ymd: str, fed_funds: dict[str, Any]) -> RawEvent:
    release_date = datetime.strptime(ymd, "%Y%m%d").replace(tzinfo=UTC)
    median_now = fed_funds["median"]
    # Title: first-year median is the most prominent dot-plot signal.
    nearest_year_key = next(iter(median_now))
    title = (
        f"FOMC dot plot {release_date.date()}: "
        f"federal funds rate median {median_now[nearest_year_key]}% for {nearest_year_key}"
    )
    return RawEvent(
        source=EventSource.FOMC,
        event_type="DOT_PLOT_RELEASE",
        external_id=ymd,
        title=title[:500],
        payload={
            "release_date": release_date.date().isoformat(),
            "url": _PROJ_URL_TMPL.format(ymd=ymd),
            "fed_funds_rate": fed_funds,
        },
        affected_tickers=[],  # market-wide event
        published_at=release_date,
    )


async def fetch_new() -> list[RawEvent]:
    log = logger.bind(source="FOMC_DOT_PLOT")
    log.info("dot_plot.fetch.started")

    calendars_html = await _fetch_html(CALENDARS_URL)
    if calendars_html is None:
        log.warning("dot_plot.calendars.unavailable")
        return []

    release_ymds = _extract_release_dates(calendars_html)[:_INGEST_RECENT_N]

    # Skip future-dated releases that the calendar page might list pre-emptively.
    today = datetime.now(UTC) + timedelta(days=1)  # +1 day for tz safety
    release_ymds = [
        ymd for ymd in release_ymds if datetime.strptime(ymd, "%Y%m%d") <= today.replace(tzinfo=None)
    ]

    events: list[RawEvent] = []
    for ymd in release_ymds:
        url = _PROJ_URL_TMPL.format(ymd=ymd)
        html = await _fetch_html(url)
        if html is None:
            continue
        fed_funds = _parse_projection_table(html)
        if fed_funds is None:
            log.warning("dot_plot.fedfunds.missing", ymd=ymd)
            continue
        events.append(_to_raw_event(ymd, fed_funds))

    log.info("dot_plot.fetch.completed", parsed=len(events))
    return events
