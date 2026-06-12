"""Response models for GET /api/v1/pnl — simulated fixed-stake trading P&L.

Conventions:
  - *_usd fields are dollars (already multiplied by the stake).
  - *_pct fields are fractions (0.0123 = +1.23%), matching accuracy's
    alignment_rate convention; the frontend multiplies by 100.
  - Ratios are None (not 0) when there is no data to divide by.
"""

from datetime import datetime

from pydantic import BaseModel

from app.db.models import OutcomeWindow, PredictionDirection


class PnlStats(BaseModel):
    """Aggregate result of following every directional call in one slice."""

    trades: int  # executed positions (BULLISH/BEARISH calls with an outcome)
    neutral_skipped: int  # NEUTRAL calls — no position, no capital deployed
    invested_usd: float  # stake x trades (total notional put at risk)
    pnl_usd: float
    return_pct: float | None  # pnl_usd / invested_usd
    wins: int  # trades with pnl > 0
    losses: int  # trades with pnl < 0 (pnl == 0 counts as neither)
    win_rate: float | None  # wins / trades
    # Same stakes, same windows, but always long SPY instead of following
    # the model — "what if I'd just bought the index each time".
    spy_pnl_usd: float
    spy_return_pct: float | None


class WeightedPnl(BaseModel):
    """Confidence-weighted variant: each trade stakes stake x confidence."""

    invested_usd: float
    pnl_usd: float
    return_pct: float | None


class GroupPnl(BaseModel):
    """P&L breakdown row for one label of a dimension (window/model/...)."""

    label: str
    trades: int
    invested_usd: float
    pnl_usd: float
    return_pct: float | None
    win_rate: float | None


class PnlTrade(BaseModel):
    """One simulated trade — used for best/worst callouts."""

    ticker: str
    window: OutcomeWindow
    direction: PredictionDirection  # the acted call (7d uses direction_7d)
    confidence: float
    model: str
    event_title: str
    entered_at: datetime
    exited_at: datetime  # nominal exit: entered_at + window duration
    ticker_return: float
    pnl_usd: float


class EquityPoint(BaseModel):
    """Cumulative P&L after each trade, ordered by nominal exit time."""

    t: datetime  # exit time of the trade that realizes this pnl
    pnl_usd: float  # cumulative strategy P&L
    spy_pnl_usd: float  # cumulative always-long-SPY benchmark P&L
    ticker: str
    window: OutcomeWindow
    direction: PredictionDirection
    trade_pnl_usd: float  # this trade's own contribution


class PnlResponse(BaseModel):
    stake_usd: float
    total: PnlStats
    weighted: WeightedPnl
    by_window: list[GroupPnl]
    by_model: list[GroupPnl]
    by_ticker: list[GroupPnl]
    by_confidence: list[GroupPnl]
    equity_curve: list[EquityPoint]
    best_trade: PnlTrade | None
    worst_trade: PnlTrade | None
    period_start: datetime | None  # earliest prediction in the filtered set
    period_end: datetime | None  # latest nominal exit among executed trades
    filters: dict[str, str | None]
