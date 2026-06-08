"""Unit tests for the FRED daily-yield indicator adapter — no HTTP, no DB."""

from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.indicators_fred import (
    FRED_INDICATOR_SERIES,
    fetch_new,
)


@pytest.fixture(autouse=True)
def _set_fred_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key-12345")
    from app.config.settings import get_settings

    get_settings.cache_clear()


async def test_fetch_new_returns_observations_per_series() -> None:
    """One IndicatorObservation per (series, date) row; missing-data marker skipped."""
    rows = [
        {"date": "2026-06-06", "value": "4.32"},
        {"date": "2026-06-05", "value": "."},  # missing — skip
        {"date": "2026-06-04", "value": "4.28"},
    ]
    with patch(
        "app.adapters.indicators_fred._fetch_series_observations",
        new=AsyncMock(return_value=rows),
    ):
        obs = await fetch_new()

    # 2 valid rows x 2 series (DGS10, DGS2) = 4
    assert len(obs) == 2 * len(FRED_INDICATOR_SERIES)
    assert {o.source for o in obs} == {"FRED"}
    assert {o.indicator_key for o in obs} == {"DGS10", "DGS2"}


async def test_fetch_new_observation_carries_correct_value_and_key() -> None:
    rows = [{"date": "2026-06-06", "value": "4.32"}]
    with patch(
        "app.adapters.indicators_fred._fetch_series_observations",
        new=AsyncMock(return_value=rows),
    ):
        obs = await fetch_new()

    keys_by_obs = {o.indicator_key: o for o in obs}
    assert keys_by_obs["DGS10"].value == 4.32
    assert keys_by_obs["DGS10"].payload["series_id"] == "DGS10"
    assert keys_by_obs["DGS2"].observed_at.date().isoformat() == "2026-06-06"


async def test_fetch_new_drops_unparseable_value() -> None:
    rows = [
        {"date": "2026-06-06", "value": "not-a-number"},
        {"date": "2026-06-05", "value": None},
    ]
    with patch(
        "app.adapters.indicators_fred._fetch_series_observations",
        new=AsyncMock(return_value=rows),
    ):
        obs = await fetch_new()
    assert obs == []
