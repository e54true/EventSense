"""Unit tests for FRED adapter — parsing logic, no real HTTP, no DB.

We use pytest-httpx to intercept httpx requests. The adapter's DB writes are tested
in tests/integration/test_fred_idempotency.py against a real Postgres.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.adapters.fred import FRED_API_BASE, _fetch_series_observations, fetch_cpi


@pytest.fixture(autouse=True)
def _set_fred_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this file needs FRED_API_KEY set; reset get_settings cache too."""
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
    assert result[0]["value"] == "332.4"


async def test_fetch_observations_raises_on_5xx(httpx_mock: HTTPXMock) -> None:
    # 4 attempts (tenacity stop_after_attempt(4)) all fail → final HTTPStatusError reraised.
    for _ in range(4):
        httpx_mock.add_response(status_code=503)
    with pytest.raises(httpx.HTTPStatusError):
        await _fetch_series_observations("CPIAUCSL")


async def test_fetch_cpi_skips_missing_value() -> None:
    """Observations with value=='.' (FRED's missing-data marker) must be skipped silently."""
    observations = [
        {"date": "2026-04-01", "value": "332.4"},
        {"date": "2026-03-01", "value": "."},  # missing — should be skipped
        {"date": "2026-02-01", "value": "327.5"},
    ]
    # db.add is sync in SQLAlchemy; everything else is async. Mix mock types accordingly.
    fake_db = AsyncMock()
    fake_db.add = MagicMock()
    fake_db.scalar = AsyncMock(return_value=None)  # nothing exists yet
    fake_db.flush = AsyncMock()
    fake_db.commit = AsyncMock()

    with patch(
        "app.adapters.fred._fetch_series_observations",
        new=AsyncMock(return_value=observations),
    ):
        inserted = await fetch_cpi(fake_db)

    # 2 valid observations queued, the "." row skipped.
    assert inserted == 2
    assert fake_db.add.call_count == 2


async def test_fetch_cpi_raises_runtime_error_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRED_API_KEY", "")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    fake_db = AsyncMock()
    with pytest.raises(RuntimeError, match="FRED_API_KEY not configured"):
        await fetch_cpi(fake_db)
