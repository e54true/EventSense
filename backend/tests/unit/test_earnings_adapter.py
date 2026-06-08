"""Unit tests for earnings adapter — parsing yfinance.earnings_history.

We don't hit yfinance for real (it's flaky and gives different data each run);
we mock the DataFrame shape it returns.
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from app.adapters.earnings import (
    _build_fundamentals,
    _earnings_history_rows,
    _fetch_income_stmt_by_quarter,
    _row_to_raw_event,
    _safe_float,
    _yoy_growth_pct,
    fetch_new,
)
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


def test_earnings_history_rows_converts_decimal_to_percent() -> None:
    """yfinance returns surprisePercent as a decimal (0.0554); we normalize to 5.54."""
    df = pd.DataFrame(
        {
            "epsActual": [1.87],
            "epsEstimate": [1.77],
            "surprisePercent": [0.0554],
        },
        index=pd.to_datetime(["2026-04-30"], utc=True),
    )
    fake_ticker = type("T", (), {"earnings_history": df})()
    with patch("app.adapters.earnings.yf.Ticker", return_value=fake_ticker):
        rows = _earnings_history_rows("NVDA")
    assert len(rows) == 1
    assert rows[0]["surprise_pct"] == pytest.approx(5.54)


async def test_fetch_new_returns_empty_on_yfinance_exception() -> None:
    """yfinance crashing must not crash the task — just yield no events."""

    def _explode(_ticker: str) -> pd.DataFrame:
        raise RuntimeError("yfinance died")

    with patch("app.adapters.earnings.yf.Ticker") as mock_ticker:
        mock_ticker.side_effect = _explode
        events = await fetch_new()
    assert events == []


# ---- Phase A: fundamentals from quarterly_income_stmt ----


def _income_stmt_df() -> pd.DataFrame:
    """5-quarter DataFrame mirroring yfinance.quarterly_income_stmt shape.

    Columns newest-first; rows are the standard income statement labels we
    extract. Values are realistic NVDA-scale numbers for testing Y/Y math.
    """
    quarters = pd.to_datetime(
        ["2026-04-30", "2026-01-31", "2025-10-31", "2025-07-31", "2025-04-30"]
    )
    rows = {
        "Total Revenue": [81.6e9, 60.0e9, 50.0e9, 45.0e9, 44.0e9],
        "Gross Profit": [61.2e9, 45.0e9, 37.0e9, 33.0e9, 26.7e9],
        "Cost Of Revenue": [20.5e9, 15.0e9, 13.0e9, 12.0e9, 17.4e9],
        "Operating Income": [53.5e9, 40.0e9, 32.0e9, 28.0e9, 21.6e9],
        "Net Income": [58.3e9, 43.0e9, 35.0e9, 30.0e9, 18.8e9],
        "EBITDA": [71.0e9, 53.0e9, 43.0e9, 38.0e9, 22.6e9],
        "Research And Development": [6.32e9, 5.5e9, 4.8e9, 4.2e9, 3.99e9],
        "Diluted EPS": [2.39, 1.78, 1.45, 1.24, 0.76],
    }
    return pd.DataFrame(rows, index=quarters).T


def test_fetch_income_stmt_by_quarter_parses_5_quarters() -> None:
    fake_ticker = type("T", (), {"quarterly_income_stmt": _income_stmt_df()})()
    with patch("app.adapters.earnings.yf.Ticker", return_value=fake_ticker):
        result = _fetch_income_stmt_by_quarter("NVDA")
    assert result is not None
    assert date(2026, 4, 30) in result
    latest = result[date(2026, 4, 30)]
    assert latest["revenue"] == pytest.approx(81.6e9)
    assert latest["net_income"] == pytest.approx(58.3e9)
    assert latest["diluted_eps"] == pytest.approx(2.39)


def test_fetch_income_stmt_returns_none_on_yfinance_exception() -> None:
    def _explode(_ticker: str) -> pd.DataFrame:
        raise RuntimeError("yfinance died")

    with patch("app.adapters.earnings.yf.Ticker", side_effect=_explode):
        assert _fetch_income_stmt_by_quarter("NVDA") is None


def test_fetch_income_stmt_returns_none_on_empty_df() -> None:
    fake_ticker = type("T", (), {"quarterly_income_stmt": pd.DataFrame()})()
    with patch("app.adapters.earnings.yf.Ticker", return_value=fake_ticker):
        assert _fetch_income_stmt_by_quarter("NVDA") is None


def test_yoy_growth_uses_same_quarter_previous_year() -> None:
    fake_ticker = type("T", (), {"quarterly_income_stmt": _income_stmt_df()})()
    with patch("app.adapters.earnings.yf.Ticker", return_value=fake_ticker):
        by_q = _fetch_income_stmt_by_quarter("NVDA")
    assert by_q is not None
    yoy = _yoy_growth_pct(by_q, date(2026, 4, 30))
    # Revenue: 81.6 vs 44.0 = +85.45%
    assert yoy["revenue_yoy_pct"] == pytest.approx(85.45, abs=0.1)
    # Net income: 58.3 vs 18.8 = +210.11%
    assert yoy["net_income_yoy_pct"] == pytest.approx(210.11, abs=0.1)


def test_yoy_returns_empty_when_no_prior_year_match() -> None:
    """A quarter with no ~365-day-prior column → empty Y/Y dict (graceful)."""
    fake_ticker = type("T", (), {"quarterly_income_stmt": _income_stmt_df()})()
    with patch("app.adapters.earnings.yf.Ticker", return_value=fake_ticker):
        by_q = _fetch_income_stmt_by_quarter("NVDA")
    assert by_q is not None
    # 2025-07-31 has no 2024-07-31 counterpart in our fixture
    yoy = _yoy_growth_pct(by_q, date(2025, 7, 31))
    assert yoy == {}


def test_build_fundamentals_combines_quarter_with_yoy() -> None:
    by_q = {
        date(2026, 4, 30): {"revenue": 100.0, "net_income": 50.0},
        date(2025, 4, 30): {"revenue": 80.0, "net_income": 25.0},
    }
    f = _build_fundamentals(by_q, date(2026, 4, 30))
    assert f is not None
    assert f["revenue"] == 100.0
    assert f["revenue_yoy_pct"] == pytest.approx(25.0)
    assert f["net_income_yoy_pct"] == pytest.approx(100.0)


def test_build_fundamentals_returns_none_when_quarter_missing() -> None:
    by_q = {date(2025, 4, 30): {"revenue": 80.0}}
    assert _build_fundamentals(by_q, date(2026, 4, 30)) is None


def test_build_fundamentals_returns_none_when_income_stmt_unavailable() -> None:
    assert _build_fundamentals(None, date(2026, 4, 30)) is None


def test_row_to_raw_event_includes_fundamentals_when_provided() -> None:
    row = {
        "report_date": datetime(2026, 4, 30, tzinfo=UTC),
        "eps_actual": 1.87,
        "eps_estimate": 1.77,
        "surprise_pct": 5.5,
    }
    fundamentals = {"revenue": 81.6e9, "revenue_yoy_pct": 85.0}
    event = _row_to_raw_event("NVDA", row, fundamentals)
    assert event is not None
    assert event.payload["fundamentals"] == fundamentals


def test_row_to_raw_event_omits_fundamentals_key_when_none() -> None:
    """No fundamentals available → payload doesn't include the key at all
    (LLM prompt then doesn't pretend they exist as null)."""
    row = {
        "report_date": datetime(2026, 4, 30, tzinfo=UTC),
        "eps_actual": 1.87,
        "eps_estimate": 1.77,
        "surprise_pct": 5.5,
    }
    event = _row_to_raw_event("NVDA", row, None)
    assert event is not None
    assert "fundamentals" not in event.payload
