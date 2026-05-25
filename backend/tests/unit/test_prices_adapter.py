"""Unit tests for prices adapter — yfinance wrapper behavior under good/bad data."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd

from app.adapters.prices import _yf_history


def _fake_ticker(df: pd.DataFrame | None) -> MagicMock:
    """Build a MagicMock that quacks like yfinance.Ticker for our tests."""
    mock = MagicMock()
    mock.history.return_value = df if df is not None else pd.DataFrame()
    return mock


def test_yf_history_parses_close_to_decimal() -> None:
    df = pd.DataFrame(
        {
            "Open": [180.0, 181.0],
            "High": [182.0, 182.5],
            "Low": [179.0, 180.5],
            "Close": [181.25, 182.10],
            "Volume": [1_000_000, 1_200_000],
        },
        index=pd.DatetimeIndex(
            [datetime(2026, 5, 1, 14, 30, tzinfo=UTC), datetime(2026, 5, 1, 14, 31, tzinfo=UTC)],
            tz="UTC",
        ),
    )
    with patch("app.adapters.prices.yf.Ticker", return_value=_fake_ticker(df)):
        ticks = _yf_history("AAPL", period="5d", interval="1m")
    assert len(ticks) == 2
    assert ticks[0].ticker == "AAPL"
    assert ticks[0].price == Decimal("181.2500")
    assert ticks[1].price == Decimal("182.1000")
    assert ticks[0].snapshot_at.tzinfo is not None  # tz-aware


def test_yf_history_empty_df_returns_empty_list() -> None:
    with patch("app.adapters.prices.yf.Ticker", return_value=_fake_ticker(pd.DataFrame())):
        assert _yf_history("AAPL", period="5d", interval="1m") == []


def test_yf_history_swallows_yfinance_exceptions() -> None:
    """yfinance.Ticker(...).history() may raise RuntimeError, KeyError, etc.
    Adapter must return [] not propagate.
    """
    mock = MagicMock()
    mock.history.side_effect = RuntimeError("yfinance changed their HTML")
    with patch("app.adapters.prices.yf.Ticker", return_value=mock):
        assert _yf_history("AAPL", period="5d", interval="1m") == []
