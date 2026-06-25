"""Simulated fixed-stake trading P&L over validated prediction outcomes.

The question this answers: "if I had placed a fixed-size position on every
directional call the system made, from the first event onward, where would I
be now?" Per validated (prediction, window) outcome:

    BULLISH → long  $stake → pnl = stake x ticker_return
    BEARISH → short $stake → pnl = stake x (-ticker_return)
    NEUTRAL → no position  → pnl = 0, no capital deployed (counted, not traded)

Modeling notes (kept deliberately simple — this measures signal quality, not
brokerage reality):
  - Shorting is pure notional inversion: profit when the price falls. No
    borrow fees, margin interest, slippage, or commissions on either side.
  - Entry uses the same anchor the validator scored against (predicted_at →
    baseline_price), exit is the outcome window's end price, so P&L is exactly
    stake x the stored ticker_return — no re-derivation from prices.
  - Trades overlap in time across tickers and windows, so there is no single
    compounding bankroll. The honest aggregate is return on deployed capital:
    Σpnl / (stake x trades), i.e. the average per-stake return.
  - The 7d leg trades direction_7d when present, mirroring the validator's
    per-window direction selection (validator._build_outcome).
  - The 1h window is legacy (no longer validated) and is excluded.

The SPY benchmark answers "was following the model better than mindlessly
buying the index with the same stakes?": same trade set, same windows, but
always long SPY, using the outcome row's stored spy_return.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.db.models import OutcomeWindow, PredictionDirection
from app.schemas.pnl import (
    EquityPoint,
    GroupPnl,
    PnlResponse,
    PnlStats,
    PnlTrade,
    WeightedPnl,
)

# Nominal holding periods. H1 is intentionally absent — legacy rows are
# filtered out (also at the query level in the route).
_WINDOW_DURATIONS: dict[OutcomeWindow, timedelta] = {
    OutcomeWindow.H24: timedelta(hours=24),
    OutcomeWindow.D7: timedelta(days=7),
}

# Same boundaries as the accuracy route's calibration table
# (app/api/routes/accuracy.py::_CALIBRATION_BUCKETS) so the two dashboards
# line up bucket-for-bucket. [lo, hi) except the last.
_CONFIDENCE_BUCKETS: list[tuple[float, float]] = [
    (0.0, 0.55),
    (0.55, 0.65),
    (0.65, 0.75),
    (0.75, 0.85),
    (0.85, 1.01),
]


@dataclass(frozen=True)
class SimTrade:
    """One validated outcome row, pre-joined with its prediction + event."""

    window: OutcomeWindow
    direction: PredictionDirection
    direction_7d: PredictionDirection | None
    confidence: float
    ticker: str
    model: str
    event_title: str
    predicted_at: datetime
    ticker_return: float
    spy_return: float


@dataclass(frozen=True)
class _Executed:
    """A SimTrade that actually opened a position (non-NEUTRAL)."""

    ticker: str
    window: OutcomeWindow
    direction: PredictionDirection
    confidence: float
    model: str
    event_title: str
    entered_at: datetime
    exited_at: datetime
    ticker_return: float
    pnl: float
    spy_pnl: float
    weighted_stake: float
    weighted_pnl: float


def effective_direction(row: SimTrade) -> PredictionDirection:
    """The call that gets traded for this window — 7d prefers direction_7d."""
    if row.window == OutcomeWindow.D7 and row.direction_7d is not None:
        return row.direction_7d
    return row.direction


def _ratio(numerator: float, denominator: float) -> float | None:
    return (numerator / denominator) if denominator > 0 else None


def _sharpe(per_trade_returns: list[float]) -> float | None:
    n = len(per_trade_returns)
    if n < 2:
        return None
    mean = sum(per_trade_returns) / n
    variance = sum((r - mean) ** 2 for r in per_trade_returns) / (n - 1)
    std = variance ** 0.5
    return (mean / std) if std > 0 else None


def _sharpe_annualized(
    per_trade_sharpe: float | None,
    executed: list[_Executed],
) -> float | None:
    if per_trade_sharpe is None or len(executed) < 2:
        return None
    span_days = (
        executed[-1].exited_at - executed[0].entered_at
    ).total_seconds() / 86_400
    if span_days <= 0:
        return None
    trades_per_year = len(executed) / (span_days / 365.25)
    return per_trade_sharpe * (trades_per_year ** 0.5)


def _max_drawdown(executed: list[_Executed]) -> tuple[float, float | None]:
    cum = peak = max_dd = 0.0
    for t in executed:
        cum += t.pnl
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    return max_dd, (max_dd / peak if peak > 0 else None)


def _stats(executed: list[_Executed], neutral_skipped: int, stake_usd: float) -> PnlStats:
    invested = stake_usd * len(executed)
    pnl = sum(t.pnl for t in executed)
    spy_pnl = sum(t.spy_pnl for t in executed)
    wins = sum(1 for t in executed if t.pnl > 0)
    losses = sum(1 for t in executed if t.pnl < 0)
    per_trade_returns = [t.pnl / stake_usd for t in executed]
    mdd_usd, mdd_pct = _max_drawdown(executed)
    sharpe = _sharpe(per_trade_returns)
    return PnlStats(
        trades=len(executed),
        neutral_skipped=neutral_skipped,
        invested_usd=invested,
        pnl_usd=pnl,
        return_pct=_ratio(pnl, invested),
        wins=wins,
        losses=losses,
        win_rate=_ratio(wins, len(executed)),
        spy_pnl_usd=spy_pnl,
        spy_return_pct=_ratio(spy_pnl, invested),
        sharpe_ratio=sharpe,
        sharpe_annualized=_sharpe_annualized(sharpe, executed),
        mdd_usd=mdd_usd,
        mdd_pct=mdd_pct,
    )


def _group(label: str, executed: list[_Executed], stake_usd: float) -> GroupPnl:
    invested = stake_usd * len(executed)
    pnl = sum(t.pnl for t in executed)
    wins = sum(1 for t in executed if t.pnl > 0)
    return GroupPnl(
        label=label,
        trades=len(executed),
        invested_usd=invested,
        pnl_usd=pnl,
        return_pct=_ratio(pnl, invested),
        win_rate=_ratio(wins, len(executed)),
    )


def _trade_out(t: _Executed) -> PnlTrade:
    return PnlTrade(
        ticker=t.ticker,
        window=t.window,
        direction=t.direction,
        confidence=t.confidence,
        model=t.model,
        event_title=t.event_title,
        entered_at=t.entered_at,
        exited_at=t.exited_at,
        ticker_return=t.ticker_return,
        pnl_usd=t.pnl,
    )


def simulate(
    rows: list[SimTrade],
    stake_usd: float,
    filters: dict[str, str | None],
) -> PnlResponse:
    """Run the fixed-stake strategy over `rows` and assemble the API response.

    Pure function of its inputs — no DB, no clock — so the whole aggregation
    is unit-testable (same rationale as services/alignment.py).
    """
    executed: list[_Executed] = []
    neutral_skipped = 0

    for row in rows:
        duration = _WINDOW_DURATIONS.get(row.window)
        if duration is None:  # legacy 1h rows — defense in depth vs the query
            continue
        direction = effective_direction(row)
        if direction == PredictionDirection.NEUTRAL:
            neutral_skipped += 1
            continue
        sign = 1.0 if direction == PredictionDirection.BULLISH else -1.0
        weighted_stake = stake_usd * row.confidence
        executed.append(
            _Executed(
                ticker=row.ticker,
                window=row.window,
                direction=direction,
                confidence=row.confidence,
                model=row.model,
                event_title=row.event_title,
                entered_at=row.predicted_at,
                exited_at=row.predicted_at + duration,
                ticker_return=row.ticker_return,
                pnl=stake_usd * sign * row.ticker_return,
                spy_pnl=stake_usd * row.spy_return,
                weighted_stake=weighted_stake,
                weighted_pnl=weighted_stake * sign * row.ticker_return,
            )
        )

    # P&L realizes at exit; a 24h trade entered after a 7d trade can still
    # exit first. Ticker/window tie-breaks keep the curve deterministic.
    executed.sort(key=lambda t: (t.exited_at, t.ticker, t.window.value))

    curve: list[EquityPoint] = []
    cum = 0.0
    cum_spy = 0.0
    for t in executed:
        cum += t.pnl
        cum_spy += t.spy_pnl
        curve.append(
            EquityPoint(
                t=t.exited_at,
                pnl_usd=cum,
                spy_pnl_usd=cum_spy,
                ticker=t.ticker,
                window=t.window,
                direction=t.direction,
                trade_pnl_usd=t.pnl,
            )
        )

    by_window = [
        _group(w.value, [t for t in executed if t.window == w], stake_usd)
        for w in (OutcomeWindow.H24, OutcomeWindow.D7)
    ]
    models = sorted({t.model for t in executed})
    by_model = [_group(m, [t for t in executed if t.model == m], stake_usd) for m in models]
    by_model.sort(key=lambda g: g.pnl_usd, reverse=True)
    tickers = sorted({t.ticker for t in executed})
    by_ticker = [_group(tk, [t for t in executed if t.ticker == tk], stake_usd) for tk in tickers]
    by_ticker.sort(key=lambda g: g.pnl_usd, reverse=True)
    by_confidence = [
        _group(
            f"{lo:.2f}-{min(hi, 1.0):.2f}",
            [t for t in executed if lo <= t.confidence < hi],
            stake_usd,
        )
        for lo, hi in _CONFIDENCE_BUCKETS
    ]

    weighted_invested = sum(t.weighted_stake for t in executed)
    weighted_pnl = sum(t.weighted_pnl for t in executed)

    return PnlResponse(
        stake_usd=stake_usd,
        total=_stats(executed, neutral_skipped, stake_usd),
        weighted=WeightedPnl(
            invested_usd=weighted_invested,
            pnl_usd=weighted_pnl,
            return_pct=_ratio(weighted_pnl, weighted_invested),
        ),
        by_window=by_window,
        by_model=by_model,
        by_ticker=by_ticker,
        by_confidence=by_confidence,
        equity_curve=curve,
        best_trade=_trade_out(max(executed, key=lambda t: t.pnl)) if executed else None,
        worst_trade=_trade_out(min(executed, key=lambda t: t.pnl)) if executed else None,
        period_start=min((r.predicted_at for r in rows), default=None),
        period_end=max((t.exited_at for t in executed), default=None),
        filters=filters,
    )
