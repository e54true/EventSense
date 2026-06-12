"""Unit tests for the simulated P&L service — pure functions, no DB, no mocks."""

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import OutcomeWindow, PredictionDirection
from app.services.pnl import SimTrade, effective_direction, simulate

T0 = datetime(2026, 5, 1, 14, 0, tzinfo=UTC)


def _row(
    *,
    window: OutcomeWindow = OutcomeWindow.H24,
    direction: PredictionDirection = PredictionDirection.BULLISH,
    direction_7d: PredictionDirection | None = None,
    confidence: float = 0.7,
    ticker: str = "AAPL",
    model: str = "gpt-5-mini",
    title: str = "test event",
    predicted_at: datetime = T0,
    ticker_return: float = 0.02,
    spy_return: float = 0.01,
) -> SimTrade:
    return SimTrade(
        window=window,
        direction=direction,
        direction_7d=direction_7d,
        confidence=confidence,
        ticker=ticker,
        model=model,
        event_title=title,
        predicted_at=predicted_at,
        ticker_return=ticker_return,
        spy_return=spy_return,
    )


_NO_FILTERS: dict[str, str | None] = {}


# --- effective_direction ---


def test_24h_always_uses_primary_direction() -> None:
    row = _row(direction=PredictionDirection.BULLISH, direction_7d=PredictionDirection.BEARISH)
    assert effective_direction(row) == PredictionDirection.BULLISH


def test_7d_prefers_direction_7d() -> None:
    row = _row(
        window=OutcomeWindow.D7,
        direction=PredictionDirection.BULLISH,
        direction_7d=PredictionDirection.BEARISH,
    )
    assert effective_direction(row) == PredictionDirection.BEARISH


def test_7d_falls_back_to_primary_when_legacy() -> None:
    row = _row(window=OutcomeWindow.D7, direction=PredictionDirection.BULLISH, direction_7d=None)
    assert effective_direction(row) == PredictionDirection.BULLISH


# --- per-trade P&L sign conventions ---


def test_bullish_long_gains_when_price_rises() -> None:
    result = simulate([_row(ticker_return=0.02)], 100.0, _NO_FILTERS)
    assert result.total.pnl_usd == pytest.approx(2.0)
    assert result.total.return_pct == pytest.approx(0.02)
    assert result.total.wins == 1


def test_bullish_long_loses_when_price_falls() -> None:
    result = simulate([_row(ticker_return=-0.03)], 100.0, _NO_FILTERS)
    assert result.total.pnl_usd == pytest.approx(-3.0)
    assert result.total.losses == 1


def test_bearish_short_gains_when_price_falls() -> None:
    result = simulate(
        [_row(direction=PredictionDirection.BEARISH, ticker_return=-0.03)],
        100.0,
        _NO_FILTERS,
    )
    assert result.total.pnl_usd == pytest.approx(3.0)
    assert result.total.wins == 1


def test_bearish_short_loses_when_price_rises() -> None:
    result = simulate(
        [_row(direction=PredictionDirection.BEARISH, ticker_return=0.04)],
        100.0,
        _NO_FILTERS,
    )
    assert result.total.pnl_usd == pytest.approx(-4.0)
    assert result.total.losses == 1


def test_neutral_skips_and_deploys_no_capital() -> None:
    result = simulate(
        [_row(direction=PredictionDirection.NEUTRAL, ticker_return=0.10)],
        100.0,
        _NO_FILTERS,
    )
    assert result.total.trades == 0
    assert result.total.neutral_skipped == 1
    assert result.total.invested_usd == 0.0
    assert result.total.pnl_usd == 0.0
    assert result.total.return_pct is None
    assert result.equity_curve == []


def test_legacy_1h_rows_are_ignored() -> None:
    result = simulate([_row(window=OutcomeWindow.H1, ticker_return=0.5)], 100.0, _NO_FILTERS)
    assert result.total.trades == 0
    assert result.total.neutral_skipped == 0


def test_7d_trade_uses_the_7d_call() -> None:
    # 24h says BULLISH but the 7d call says BEARISH; price fell 2% over 7d →
    # the simulated 7d short must profit.
    result = simulate(
        [
            _row(
                window=OutcomeWindow.D7,
                direction=PredictionDirection.BULLISH,
                direction_7d=PredictionDirection.BEARISH,
                ticker_return=-0.02,
            )
        ],
        100.0,
        _NO_FILTERS,
    )
    assert result.total.pnl_usd == pytest.approx(2.0)


# --- aggregates ---


def test_return_pct_is_pnl_over_deployed_capital() -> None:
    rows = [
        _row(ticker_return=0.02),  # +$2
        _row(ticker="MSFT", ticker_return=-0.01),  # -$1
        _row(ticker="NVDA", direction=PredictionDirection.NEUTRAL),  # skipped
    ]
    result = simulate(rows, 100.0, _NO_FILTERS)
    assert result.total.trades == 2
    assert result.total.invested_usd == pytest.approx(200.0)
    assert result.total.pnl_usd == pytest.approx(1.0)
    assert result.total.return_pct == pytest.approx(0.005)
    assert result.total.win_rate == pytest.approx(0.5)


def test_spy_benchmark_is_always_long_same_stakes() -> None:
    rows = [
        _row(direction=PredictionDirection.BEARISH, ticker_return=-0.03, spy_return=0.01),
        _row(ticker="MSFT", ticker_return=0.02, spy_return=-0.005),
    ]
    result = simulate(rows, 100.0, _NO_FILTERS)
    # Strategy: +3 (short won) + 2 (long won) = +5; SPY: +1 - 0.5 = +0.5
    assert result.total.pnl_usd == pytest.approx(5.0)
    assert result.total.spy_pnl_usd == pytest.approx(0.5)
    assert result.total.spy_return_pct == pytest.approx(0.0025)


def test_confidence_weighted_variant() -> None:
    rows = [
        _row(confidence=0.9, ticker_return=0.02),  # stake 90 → +1.8
        _row(ticker="MSFT", confidence=0.5, ticker_return=-0.02),  # stake 50 → -1.0
    ]
    result = simulate(rows, 100.0, _NO_FILTERS)
    assert result.weighted.invested_usd == pytest.approx(140.0)
    assert result.weighted.pnl_usd == pytest.approx(0.8)
    assert result.weighted.return_pct == pytest.approx(0.8 / 140.0)


def test_equity_curve_orders_by_exit_time_not_entry() -> None:
    # 7d trade enters first but exits last; the 24h trade entered a day later
    # still exits ~5 days earlier and must appear first on the curve.
    rows = [
        _row(window=OutcomeWindow.D7, ticker_return=0.05, predicted_at=T0),
        _row(ticker="MSFT", ticker_return=-0.01, predicted_at=T0 + timedelta(days=1)),
    ]
    result = simulate(rows, 100.0, _NO_FILTERS)
    assert [p.ticker for p in result.equity_curve] == ["MSFT", "AAPL"]
    assert result.equity_curve[0].t == T0 + timedelta(days=2)
    assert result.equity_curve[0].pnl_usd == pytest.approx(-1.0)
    # Curve is cumulative: -1 then -1 + 5 = +4.
    assert result.equity_curve[1].pnl_usd == pytest.approx(4.0)
    assert result.equity_curve[1].t == T0 + timedelta(days=7)
    assert result.period_start == T0
    assert result.period_end == T0 + timedelta(days=7)


def test_group_breakdowns() -> None:
    rows = [
        _row(ticker_return=0.02, model="gpt-5"),  # 24h, +2
        _row(
            window=OutcomeWindow.D7,
            direction_7d=PredictionDirection.BULLISH,
            ticker_return=0.03,
            model="gpt-5-mini",
        ),  # 7d, +3
        _row(ticker="MSFT", ticker_return=-0.01, model="gpt-5"),  # 24h, -1
    ]
    result = simulate(rows, 100.0, _NO_FILTERS)

    windows = {g.label: g for g in result.by_window}
    assert windows["24h"].trades == 2
    assert windows["24h"].pnl_usd == pytest.approx(1.0)
    assert windows["7d"].pnl_usd == pytest.approx(3.0)

    models = {g.label: g for g in result.by_model}
    assert models["gpt-5"].pnl_usd == pytest.approx(1.0)
    assert models["gpt-5-mini"].pnl_usd == pytest.approx(3.0)
    # Sorted by pnl desc.
    assert result.by_model[0].label == "gpt-5-mini"

    tickers = {g.label: g for g in result.by_ticker}
    assert tickers["AAPL"].trades == 2
    assert tickers["MSFT"].pnl_usd == pytest.approx(-1.0)


def test_confidence_buckets_match_accuracy_boundaries() -> None:
    rows = [
        _row(confidence=0.6, ticker_return=0.02),
        _row(ticker="MSFT", confidence=0.9, ticker_return=-0.01),
    ]
    result = simulate(rows, 100.0, _NO_FILTERS)
    buckets = {g.label: g for g in result.by_confidence}
    assert set(buckets) == {"0.00-0.55", "0.55-0.65", "0.65-0.75", "0.75-0.85", "0.85-1.00"}
    assert buckets["0.55-0.65"].trades == 1
    assert buckets["0.55-0.65"].pnl_usd == pytest.approx(2.0)
    assert buckets["0.85-1.00"].pnl_usd == pytest.approx(-1.0)
    assert buckets["0.00-0.55"].trades == 0
    assert buckets["0.00-0.55"].return_pct is None


def test_best_and_worst_trades() -> None:
    rows = [
        _row(ticker_return=0.02),
        _row(ticker="MSFT", direction=PredictionDirection.BEARISH, ticker_return=-0.06),
        _row(ticker="NVDA", ticker_return=-0.04),
    ]
    result = simulate(rows, 100.0, _NO_FILTERS)
    assert result.best_trade is not None
    assert result.best_trade.ticker == "MSFT"
    assert result.best_trade.pnl_usd == pytest.approx(6.0)
    assert result.best_trade.direction == PredictionDirection.BEARISH
    assert result.worst_trade is not None
    assert result.worst_trade.ticker == "NVDA"
    assert result.worst_trade.pnl_usd == pytest.approx(-4.0)


def test_empty_input_returns_zero_state() -> None:
    result = simulate([], 100.0, _NO_FILTERS)
    assert result.total.trades == 0
    assert result.total.return_pct is None
    assert result.best_trade is None
    assert result.worst_trade is None
    assert result.period_start is None
    assert result.period_end is None
    assert result.equity_curve == []


def test_stake_scales_linearly() -> None:
    rows = [_row(ticker_return=0.02)]
    small = simulate(rows, 100.0, _NO_FILTERS)
    big = simulate(rows, 1000.0, _NO_FILTERS)
    assert big.total.pnl_usd == pytest.approx(10 * small.total.pnl_usd)
    assert big.total.return_pct == pytest.approx(small.total.return_pct)
