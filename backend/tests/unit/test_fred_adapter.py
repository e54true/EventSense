"""Unit tests for FRED adapter — parsing + multi-series iteration, no real HTTP, no DB.

The adapter is pure (returns list[RawEvent]); persistence is tested in
tests/integration/test_event_writer.py.

fetch_new() runs in ALFRED (vintage) mode: each observation row carries a
realtime_start = when that value became public; the first vintage per
reference period is the original release. published_at must anchor on that
release date (08:30 ET), NOT the reference period.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.adapters.fred import (
    FRED_API_BASE,
    FRED_EVENT_SERIES,
    _fetch_series_observations,
    _first_releases,
    fetch_new,
)
from app.db.models import EventSource


@pytest.fixture(autouse=True)
def _set_fred_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key-12345")
    from app.config.settings import get_settings

    get_settings.cache_clear()


async def test_fetch_observations_returns_parsed_list(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{FRED_API_BASE}/series/observations?series_id=CPIAUCSL&api_key=test-key-12345&file_type=json&sort_order=desc&limit=12",
        json={
            "observations": [
                {"date": "2026-04-01", "value": "332.4", "realtime_start": "2026-05-12"},
                {"date": "2026-03-01", "value": "330.3", "realtime_start": "2026-04-10"},
            ]
        },
    )
    result = await _fetch_series_observations("CPIAUCSL")
    assert len(result) == 2
    assert result[0]["date"] == "2026-04-01"


async def test_fetch_observations_raises_on_5xx(httpx_mock: HTTPXMock) -> None:
    # 4 attempts (tenacity stop_after_attempt(4)) all fail → final HTTPStatusError reraised.
    for _ in range(4):
        httpx_mock.add_response(status_code=503)
    with pytest.raises(httpx.HTTPStatusError):
        await _fetch_series_observations("CPIAUCSL")


def test_first_releases_picks_earliest_vintage_per_period() -> None:
    """Multiple vintages of the same reference period → keep the original print."""
    rows = [
        # March: first release 332.1 on Apr 10, later revised to 332.4 on May 12.
        {"date": "2026-03-01", "value": "332.1", "realtime_start": "2026-04-10"},
        {"date": "2026-03-01", "value": "332.4", "realtime_start": "2026-05-12"},
        # February: single vintage.
        {"date": "2026-02-01", "value": "330.3", "realtime_start": "2026-03-12"},
        # Missing / garbage rows are skipped.
        {"date": "2026-01-01", "value": ".", "realtime_start": "2026-02-11"},
        {"date": "2025-12-01", "value": "n/a", "realtime_start": "2026-01-13"},
    ]
    releases = _first_releases(rows)
    assert [(r.reference_period, r.release_date, r.value) for r in releases] == [
        ("2026-02-01", "2026-03-12", 330.3),
        ("2026-03-01", "2026-04-10", 332.1),
    ]


async def test_fetch_new_skips_missing_value() -> None:
    """value=='.' (FRED's missing-data marker) and non-numeric values must be skipped.

    Mock returns the same observation list for every series, so the assertions
    are per-series (n_events_per_series * len(FRED_EVENT_SERIES)).
    """
    observations = [
        {"date": "2026-04-01", "value": "332.4", "realtime_start": "2026-05-12"},
        {"date": "2026-03-01", "value": ".", "realtime_start": "2026-04-10"},  # skip
        {"date": "2026-02-01", "value": "n/a", "realtime_start": "2026-03-11"},  # skip
        {"date": "2026-01-01", "value": "327.5", "realtime_start": "2026-02-11"},
    ]
    with patch(
        "app.adapters.fred._fetch_series_vintages",
        new=AsyncMock(return_value=observations),
    ):
        events = await fetch_new()

    # 2 valid rows x 3 series in FRED_EVENT_SERIES = 6 events
    assert len(events) == 2 * len(FRED_EVENT_SERIES)
    assert all(e.source == EventSource.FRED for e in events)


async def test_fetch_new_anchors_published_at_on_release_date() -> None:
    """published_at = first-vintage realtime_start @ 08:30 ET, not the reference period."""
    observations = [
        {"date": "2026-04-01", "value": "332.4", "realtime_start": "2026-05-12"},
    ]
    with patch(
        "app.adapters.fred._fetch_series_vintages",
        new=AsyncMock(return_value=observations),
    ):
        events = await fetch_new()

    for e in events:
        # 2026-05-12 is during EDT (UTC-4): 08:30 ET == 12:30 UTC.
        assert e.published_at.isoformat() == "2026-05-12T12:30:00+00:00"
        assert e.payload["reference_period"] == "2026-04-01"
        assert e.payload["release_date"] == "2026-05-12"


async def test_fetch_new_emits_distinct_external_id_per_series() -> None:
    """Each series writes its own (series_id:period) external_id — no cross-series collision."""
    observations = [
        {"date": "2026-04-01", "value": "1.23", "realtime_start": "2026-05-12"},
    ]
    with patch(
        "app.adapters.fred._fetch_series_vintages",
        new=AsyncMock(return_value=observations),
    ):
        events = await fetch_new()

    external_ids = {e.external_id for e in events}
    expected = {f"{spec.series_id}:2026-04-01" for spec in FRED_EVENT_SERIES}
    assert external_ids == expected


async def test_fetch_new_event_types_align_with_spec() -> None:
    """CPI_RELEASE / NFP_RELEASE / GDP_RELEASE one event_type per series spec."""
    observations = [
        {"date": "2026-04-01", "value": "1.0", "realtime_start": "2026-05-12"},
    ]
    with patch(
        "app.adapters.fred._fetch_series_vintages",
        new=AsyncMock(return_value=observations),
    ):
        events = await fetch_new()

    by_event_type = {e.event_type for e in events}
    assert by_event_type == {spec.event_type for spec in FRED_EVENT_SERIES}
    assert "CPI_RELEASE" in by_event_type
    assert "NFP_RELEASE" in by_event_type
    assert "GDP_RELEASE" in by_event_type


async def test_fetch_new_computes_cpi_derived_metrics() -> None:
    """CPI events get MoM (and YoY with 13 periods) computed from first releases."""
    observations = [
        {"date": "2026-03-01", "value": "330.0", "realtime_start": "2026-04-10"},
        {"date": "2026-04-01", "value": "331.65", "realtime_start": "2026-05-12"},
    ]
    with patch(
        "app.adapters.fred._fetch_series_vintages",
        new=AsyncMock(return_value=observations),
    ):
        events = await fetch_new()

    cpi_events = [e for e in events if e.event_type == "CPI_RELEASE"]
    latest = max(cpi_events, key=lambda e: e.payload["reference_period"])
    # 331.65 / 330.0 - 1 = +0.5%
    assert latest.payload["derived"]["mom_pct"] == 0.5
    assert "MoM +0.50%" in latest.payload["headline"]


async def test_fetch_new_raises_runtime_error_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRED_API_KEY", "")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="FRED_API_KEY not configured"):
        await fetch_new()
