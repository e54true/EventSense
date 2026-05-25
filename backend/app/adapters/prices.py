"""Stock price adapter — wraps the unofficial yfinance library.

yfinance scrapes Yahoo Finance; it has no stability guarantees and breaks
periodically. Every public function here catches `Exception` broadly so a
yfinance regression degrades the system to "no fresh prices" instead of
crashing the worker.

We expose two granularities:
  - intraday():  recent 1-minute bars (used by the 5-min scheduler during
                 market hours; each call retrieves the last N minutes)
  - daily():     daily closes over a history window (used by the backfill
                 script on first deploy)

Both return list[PriceTick] — plain dataclasses, not Pydantic, because the
hot path is high-volume and Pydantic validation overhead matters at this
scale. The price_writer validates types on insert via SQLAlchemy.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import structlog
import yfinance as yf

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PriceTick:
    """One observation: ticker + when + close price (Decimal for $-accurate math)."""

    ticker: str
    snapshot_at: datetime  # tz-aware
    price: Decimal


def _yf_history(ticker: str, period: str, interval: str) -> list[PriceTick]:
    """Single yfinance call wrapped with broad exception isolation.

    yfinance returns a pandas DataFrame indexed by tz-aware datetime, with
    OHLCV columns. We only care about Close.
    """
    log = logger.bind(ticker=ticker, period=period, interval=interval)
    try:
        # auto_adjust=False keeps splits/dividends as separate adjustments rather
        # than mutating the close. Important for historical accuracy.
        df = yf.Ticker(ticker).history(
            period=period,
            interval=interval,
            auto_adjust=False,
        )
    except Exception as exc:
        log.warning("prices.yfinance.failed", error=str(exc))
        return []

    if df.empty:
        log.info("prices.yfinance.empty")
        return []

    ticks: list[PriceTick] = []
    for ts, row in df.iterrows():
        try:
            close = Decimal(str(row["Close"])).quantize(Decimal("0.0001"))
        except Exception:  # noqa: S112 — garbage row, skip silently to avoid log spam
            continue
        # ts is a pandas.Timestamp; convert to stdlib datetime (already tz-aware).
        snapshot_at = ts.to_pydatetime()
        ticks.append(PriceTick(ticker=ticker, snapshot_at=snapshot_at, price=close))
    return ticks


def intraday(ticker: str) -> list[PriceTick]:
    """Recent 1-minute bars. Each call grabs the last ~5 minutes of trading.

    Period '5d' is yfinance-required minimum to get 1m data; we filter ourselves
    if we only want the freshest bars.
    """
    return _yf_history(ticker, period="5d", interval="1m")


def daily(ticker: str, period: str = "1y") -> list[PriceTick]:
    """Daily closes for the backfill — one tick per trading day."""
    return _yf_history(ticker, period=period, interval="1d")
