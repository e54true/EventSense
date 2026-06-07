"""Earnings adapter — surfaces "company just reported" events via yfinance.

We poll each watchlist ticker's earnings_history (past actual EPS vs estimate)
and emit one RawEvent per recent report. The Analyzer (Milestone 5) will turn
these into per-ticker predictions.

For "upcoming earnings" (calendar) — that's metadata, not an event. We don't
emit RawEvents until the earnings have actually been reported, because the
event_type=EARNINGS_REPORT only makes sense once results are out.

Like the prices adapter, yfinance instability means every call is wrapped in
broad except.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
import yfinance as yf

from app.config.settings import get_settings
from app.db.models import EventSource
from app.schemas.raw_event import RawEvent

logger = structlog.get_logger(__name__)

# Lookback window for earnings reports. 120 days = 4 months > 1 quarter,
# guaranteeing we always capture each watchlist company's most recent report
# regardless of which week of the quarter we poll (vs. 30 days which would
# miss companies whose latest earnings landed > 1 month ago).
LOOKBACK_DAYS = 120


def _earnings_history_rows(ticker: str) -> list[dict[str, Any]]:
    """Pull rows from yfinance.Ticker(ticker).earnings_history. Empty on any failure."""
    try:
        df = yf.Ticker(ticker).earnings_history
    except Exception as exc:
        logger.warning("earnings.yfinance.failed", ticker=ticker, error=str(exc))
        return []

    if df is None or df.empty:
        return []

    # yfinance returns a DataFrame indexed by quarter-end date (tz-aware Timestamp),
    # with columns like epsActual, epsEstimate, epsDifference, surprisePercent.
    rows: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        try:
            report_date = idx.to_pydatetime()
            if report_date.tzinfo is None:
                report_date = report_date.replace(tzinfo=UTC)
            rows.append(
                {
                    "report_date": report_date,
                    "eps_actual": _safe_float(row.get("epsActual")),
                    "eps_estimate": _safe_float(row.get("epsEstimate")),
                    "surprise_pct": _safe_float(row.get("surprisePercent")),
                }
            )
        except Exception:  # noqa: S112 — bad row, skip silently
            continue
    return rows


def _safe_float(v: Any) -> float | None:
    """yfinance sometimes returns NaN, None, or weird types. Normalize to float|None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # NaN check (NaN != NaN)
    if f != f:
        return None
    return f


def _row_to_raw_event(ticker: str, row: dict[str, Any]) -> RawEvent | None:
    eps_actual = row["eps_actual"]
    if eps_actual is None:
        # Skip "future" rows in earnings_history that haven't reported yet.
        return None
    report_date: datetime = row["report_date"]
    # external_id format: TICKER:YYYY-MM-DD — quarter-end date is the natural key.
    external_id = f"{ticker}:{report_date.date().isoformat()}"
    eps_est = row["eps_estimate"]
    surprise = row["surprise_pct"]

    title_parts = [f"{ticker} earnings {report_date.date()}: EPS={eps_actual}"]
    if eps_est is not None:
        title_parts.append(f"est={eps_est}")
    if surprise is not None:
        title_parts.append(f"surprise={surprise:.1f}%")
    title = " ".join(title_parts)[:500]

    return RawEvent(
        source=EventSource.EARNINGS,
        event_type="EARNINGS_REPORT",
        external_id=external_id,
        title=title,
        payload={
            "ticker": ticker,
            "report_date": report_date.date().isoformat(),
            "eps_actual": eps_actual,
            "eps_estimate": eps_est,
            "surprise_percent": surprise,
        },
        affected_tickers=[ticker],
        published_at=report_date,
    )


async def fetch_new() -> list[RawEvent]:
    """Poll watchlist tickers and emit recent earnings reports as RawEvents."""
    tickers = get_settings().watchlist
    cutoff = datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)

    log = logger.bind(source="EARNINGS", tickers=len(tickers))
    log.info("earnings.fetch.started")

    events: list[RawEvent] = []
    for ticker in tickers:
        # SPY/QQQ are ETFs without earnings — skip cheaply.
        if ticker in {"SPY", "QQQ"}:
            continue
        rows = _earnings_history_rows(ticker)
        for row in rows:
            if row["report_date"] < cutoff:
                continue
            event = _row_to_raw_event(ticker, row)
            if event is not None:
                events.append(event)

    log.info("earnings.fetch.completed", parsed=len(events))
    return events
