"""Unit tests for earnings adapter — parsing yfinance.earnings_history.

We don't hit yfinance for real (it's flaky and gives different data each run);
we mock the DataFrame shape it returns.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from app.adapters.earnings import _row_to_raw_event, _safe_float, fetch_new
from app.db.models import EventSource


@pytest.fixture(autouse=True)
def _watchlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_TICKERS", "AAPL,SPY")
    from app.config.settings import get_settings

    get_settings.cache_clear()


def test_safe_float_handles_none_and_nan() -> None:
    assert _safe_float(None) is None
    assert _safe_float(float("nan")) is None
    assert _safe_float("abc") is None
    assert _safe_float("1.5") == 1.5
    assert _safe_float(2) == 2.0


def test_row_to_raw_event_builds_external_id_from_date() -> None:
    row = {
        "report_date": datetime(2026, 4, 30, tzinfo=UTC),
        "eps_actual": 1.50,
        "eps_estimate": 1.42,
        "surprise_pct": 5.6,
    }
    event = _row_to_raw_event("AAPL", row)
    assert event is not None
    assert event.external_id == "AAPL:2026-04-30"
    assert event.source == EventSource.EARNINGS
    assert event.event_type == "EARNINGS_REPORT"
    assert event.affected_tickers == ["AAPL"]
    assert "EPS=1.5" in event.title
    assert "surprise=5.6%" in event.title


def test_row_to_raw_event_skips_unreported() -> None:
    """Future earnings rows show up in history but with eps_actual=None — skip them."""
    row = {
        "report_date": datetime(2026, 7, 30, tzinfo=UTC),
        "eps_actual": None,
        "eps_estimate": 1.60,
        "surprise_pct": None,
    }
    assert _row_to_raw_event("AAPL", row) is None


async def test_fetch_new_skips_etfs() -> None:
    """SPY/QQQ are ETFs without earnings — adapter must not even call yfinance for them."""
    with patch("app.adapters.earnings._earnings_history_rows", return_value=[]) as mock_fetch:
        await fetch_new()
    # Only AAPL should have been queried (SPY was skipped before the yfinance call)
    called_tickers = [call.args[0] for call in mock_fetch.call_args_list]
    assert "AAPL" in called_tickers
    assert "SPY" not in called_tickers


async def test_fetch_new_filters_by_cutoff() -> None:
    now = datetime.now(UTC)
    rows = [
        {
            "report_date": now - timedelta(days=5),  # within 30-day cutoff
            "eps_actual": 1.50,
            "eps_estimate": 1.40,
            "surprise_pct": 7.0,
        },
        {
            "report_date": now - timedelta(days=200),  # too old
            "eps_actual": 1.20,
            "eps_estimate": 1.10,
            "surprise_pct": 9.0,
        },
    ]
    with patch("app.adapters.earnings._earnings_history_rows", return_value=rows):
        events = await fetch_new()
    assert len(events) == 1


async def test_fetch_new_returns_empty_on_yfinance_exception() -> None:
    """yfinance crashing must not crash the task — just yield no events."""
    def _explode(_ticker: str) -> pd.DataFrame:
        raise RuntimeError("yfinance died")

    with patch("app.adapters.earnings.yf.Ticker") as mock_ticker:
        mock_ticker.side_effect = _explode
        events = await fetch_new()
    assert events == []
