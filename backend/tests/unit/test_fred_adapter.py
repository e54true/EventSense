"""Unit tests for FRED adapter — parsing logic, no real HTTP, no DB.

The adapter is pure (returns list[RawEvent]); persistence is tested in
tests/integration/test_event_writer.py.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.adapters.fred import FRED_API_BASE, _fetch_series_observations, fetch_new
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


async def test_fetch_new_skips_missing_value() -> None:
    """value=='.' (FRED's missing-data marker) and non-numeric values must be skipped."""
    observations = [
        {"date": "2026-04-01", "value": "332.4"},
        {"date": "2026-03-01", "value": "."},      # missing — skip
        {"date": "2026-02-01", "value": "n/a"},    # garbage — skip
        {"date": "2026-01-01", "value": "327.5"},
    ]
    with patch(
        "app.adapters.fred._fetch_series_observations",
        new=AsyncMock(return_value=observations),
    ):
        events = await fetch_new()

    assert len(events) == 2
    assert all(e.source == EventSource.FRED for e in events)
    assert events[0].external_id == "CPIAUCSL:2026-04-01"
    assert events[0].payload["value"] == 332.4
    assert events[1].external_id == "CPIAUCSL:2026-01-01"


async def test_fetch_new_raises_runtime_error_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRED_API_KEY", "")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="FRED_API_KEY not configured"):
        await fetch_new()
