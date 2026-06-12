"""Earnings adapter — surfaces "company just reported" events via yfinance.

We poll each watchlist ticker's earnings_history (past actual EPS vs estimate)
and emit one RawEvent per recent report. The Analyzer (Milestone 5) will turn
these into per-ticker predictions.

For "upcoming earnings" (calendar) — that's metadata, not an event. We don't
emit RawEvents until the earnings have actually been reported, because the
event_type=EARNINGS_REPORT only makes sense once results are out.

Each row's payload is also enriched with `fundamentals` from
yfinance.quarterly_income_stmt (Phase A): Revenue, Gross Profit, Operating
Income, Net Income, EBITDA, R&D, plus Y/Y growth % for each. This gives the
v2 analyzer a vastly richer per-event context than just the EPS headline.

Like the prices adapter, yfinance instability means every call is wrapped in
broad except.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import structlog
import yfinance as yf

from app.config.cik_map import TICKER_INGEST_SINCE, TICKER_TO_CIK
from app.config.settings import get_settings
from app.db.models import EventSource
from app.schemas.raw_event import RawEvent

logger = structlog.get_logger(__name__)

# Lookback window for earnings reports. 120 days = 4 months > 1 quarter,
# guaranteeing we always capture each watchlist company's most recent report
# regardless of which week of the quarter we poll (vs. 30 days which would
# miss companies whose latest earnings landed > 1 month ago).
LOOKBACK_DAYS = 120

# yfinance row label → our payload key. Anything missing in a given quarter
# becomes None — graceful degrade rather than dropping the whole fundamentals
# block.
_INCOME_STMT_METRICS: dict[str, str] = {
    "Total Revenue": "revenue",
    "Gross Profit": "gross_profit",
    "Cost Of Revenue": "cost_of_revenue",
    "Operating Income": "operating_income",
    "Net Income": "net_income",
    "EBITDA": "ebitda",
    "Research And Development": "rd_expense",
    "Diluted EPS": "diluted_eps",
}

# Tolerance for matching "same quarter previous year" — fiscal calendars
# wobble a few days quarter to quarter (e.g. AAPL's 13-week quarters).
_YOY_DATE_TOLERANCE_DAYS = 10

# How many days AFTER quarter-end to search for the matching 8-K item 2.02
# press release. Most issuers file within 4 weeks; 60 days is comfortable
# headroom for stragglers and AAPL-style ~5-week fiscal calendars.
_SEC_LOOKUP_WINDOW_DAYS = 60
_SEC_API_TIMEOUT_SEC = 15.0


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
            # yfinance returns surprisePercent as a decimal (0.0554 = 5.54%);
            # normalize to percent form here so the rest of the pipeline (title
            # rendering, payload export) doesn't need to know yfinance's quirk.
            surprise_decimal = _safe_float(row.get("surprisePercent"))
            rows.append(
                {
                    "report_date": report_date,
                    "eps_actual": _safe_float(row.get("epsActual")),
                    "eps_estimate": _safe_float(row.get("epsEstimate")),
                    "surprise_pct": (
                        surprise_decimal * 100.0 if surprise_decimal is not None else None
                    ),
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


def _fetch_income_stmt_by_quarter(ticker: str) -> dict[date, dict[str, float | None]] | None:
    """Pull yfinance quarterly_income_stmt, return {quarter_end_date: {metric: value}}.

    None when yfinance errors out or returns empty. Each metric maps to
    float | None; an entirely missing row stores None for that metric, the
    rest of the quarter survives.
    """
    try:
        df = yf.Ticker(ticker).quarterly_income_stmt
    except Exception as exc:
        logger.warning("earnings.income_stmt.failed", ticker=ticker, error=str(exc))
        return None

    if df is None or df.empty:
        return None

    by_quarter: dict[date, dict[str, float | None]] = {}
    for col in df.columns:
        try:
            quarter_end = col.date()
        except Exception:  # noqa: S112 — malformed column index, skip silently
            continue
        q_data: dict[str, float | None] = {}
        for yf_label, payload_key in _INCOME_STMT_METRICS.items():
            try:
                v = df.loc[yf_label, col]
            except (KeyError, IndexError):
                v = None
            q_data[payload_key] = _safe_float(v)
        by_quarter[quarter_end] = q_data
    return by_quarter


def _yoy_growth_pct(
    by_quarter: dict[date, dict[str, float | None]], target_quarter: date
) -> dict[str, float | None]:
    """For each metric in the target quarter, compute Y/Y % change vs same
    quarter previous year (within ±10 days). Returns {metric}_yoy_pct keys.

    Empty dict when target quarter isn't in the data, or when no prior-year
    quarter exists within tolerance.
    """
    target = by_quarter.get(target_quarter)
    if target is None:
        return {}

    try:
        prior_target = target_quarter.replace(year=target_quarter.year - 1)
    except ValueError:
        # Feb 29 — should never happen for fiscal quarter-ends but be defensive.
        return {}

    prior: dict[str, float | None] | None = None
    for q_date, q_data in by_quarter.items():
        if abs((q_date - prior_target).days) <= _YOY_DATE_TOLERANCE_DAYS:
            prior = q_data
            break
    if prior is None:
        return {}

    yoy: dict[str, float | None] = {}
    for metric_key, latest_v in target.items():
        prior_v = prior.get(metric_key)
        if latest_v is None or prior_v is None or prior_v == 0:
            yoy[f"{metric_key}_yoy_pct"] = None
        else:
            yoy[f"{metric_key}_yoy_pct"] = round((latest_v - prior_v) / abs(prior_v) * 100, 2)
    return yoy


async def _lookup_sec_8k_filing(
    client: httpx.AsyncClient, ticker: str, report_date: date
) -> dict[str, str] | None:
    """Find the SEC 8-K item 2.02 press release matching a quarterly earnings report.

    Strategy: hit SEC submissions/CIK*.json, walk the recent filings array,
    return the first form=='8-K' with item_codes containing '2.02' filed
    within (report_date, report_date + 60d].

    Returns {accession_number, primary_doc_url, filing_date} or None on any
    failure (network error, unmapped ticker, no matching filing).
    """
    cik = TICKER_TO_CIK.get(ticker)
    if not cik:
        return None

    log = logger.bind(ticker=ticker, report_date=report_date.isoformat())
    try:
        response = await client.get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        response.raise_for_status()
        submissions = response.json()
    except Exception as exc:
        log.warning("earnings.sec_lookup.fetch_failed", error=str(exc))
        return None

    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    items_list = recent.get("items", [])
    filing_dates = recent.get("filingDate", [])
    accession_nums = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    window_end = report_date + timedelta(days=_SEC_LOOKUP_WINDOW_DAYS)

    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        items = items_list[i] if i < len(items_list) else ""
        if "2.02" not in items:
            continue
        try:
            filing_date = date.fromisoformat(filing_dates[i])
        except (ValueError, IndexError):
            continue
        if not (report_date <= filing_date <= window_end):
            continue

        accession = accession_nums[i]
        primary_doc = primary_docs[i] if i < len(primary_docs) else ""
        accession_no_dashes = accession.replace("-", "")
        doc_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession_no_dashes}/{primary_doc}"
        )
        return {
            "accession_number": accession,
            "primary_doc_url": doc_url,
            "filing_date": filing_dates[i],
        }

    return None


def _build_fundamentals(
    by_quarter: dict[date, dict[str, float | None]] | None, report_date: date
) -> dict[str, Any] | None:
    """Assemble the payload['fundamentals'] block for one earnings report.

    Returns None when no income_stmt data is available for this quarter —
    payload simply omits the fundamentals key in that case (graceful degrade).
    """
    if by_quarter is None:
        return None
    quarter_data = by_quarter.get(report_date)
    if quarter_data is None:
        return None
    return {**quarter_data, **_yoy_growth_pct(by_quarter, report_date)}


def _row_to_raw_event(
    ticker: str,
    row: dict[str, Any],
    fundamentals: dict[str, Any] | None = None,
    sec_filing: dict[str, str] | None = None,
) -> RawEvent | None:
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

    payload: dict[str, Any] = {
        "ticker": ticker,
        "report_date": report_date.date().isoformat(),
        "eps_actual": eps_actual,
        "eps_estimate": eps_est,
        "surprise_percent": surprise,
        # Yahoo Finance fallback link — always available, useful for casual exploration.
        "yahoo_finance_url": f"https://finance.yahoo.com/quote/{ticker}/",
    }
    if fundamentals is not None:
        payload["fundamentals"] = fundamentals
    if sec_filing is not None:
        # Canonical source of the actual press release. The matching 8-K event
        # (same accession_number) has the EX-99.1 body in event_documents — UI
        # can deep-link via "View SEC filing" + cross-reference the 8-K event.
        payload["sec_filing"] = sec_filing

    return RawEvent(
        source=EventSource.EARNINGS,
        event_type="EARNINGS_REPORT",
        external_id=external_id,
        title=title,
        payload=payload,
        affected_tickers=[ticker],
        published_at=report_date,
    )


async def fetch_new() -> list[RawEvent]:
    """Poll watchlist tickers and emit recent earnings reports as RawEvents.

    For each ticker we make TWO yfinance calls (earnings_history + quarterly
    income statement) plus ONE SEC submissions lookup per (ticker, quarter)
    to attach the matching 8-K item 2.02 press release URL. Any individual
    call failing yields a degraded event (missing fundamentals or sec link)
    rather than dropping the event.
    """
    settings = get_settings()
    tickers = settings.watchlist
    cutoff = datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)

    log = logger.bind(source="EARNINGS", tickers=len(tickers))
    log.info("earnings.fetch.started")

    sec_headers = {"User-Agent": settings.sec_user_agent}
    events: list[RawEvent] = []
    async with httpx.AsyncClient(
        timeout=_SEC_API_TIMEOUT_SEC, headers=sec_headers, follow_redirects=True
    ) as sec_client:
        for ticker in tickers:
            # SPY/QQQ are ETFs without earnings — skip cheaply.
            if ticker in {"SPY", "QQQ"}:
                continue
            rows = _earnings_history_rows(ticker)
            if not rows:
                continue
            # Late-added tickers start at their join date — no history backfill.
            since = TICKER_INGEST_SINCE.get(ticker)
            ticker_cutoff = cutoff
            if since is not None:
                since_dt = datetime(since.year, since.month, since.day, tzinfo=UTC)
                ticker_cutoff = max(cutoff, since_dt)
            # One income_stmt fetch per ticker, reused across all that ticker's rows.
            income_by_quarter = _fetch_income_stmt_by_quarter(ticker)
            for row in rows:
                if row["report_date"] < ticker_cutoff:
                    continue
                quarter_date = row["report_date"].date()
                fundamentals = _build_fundamentals(income_by_quarter, quarter_date)
                sec_filing = await _lookup_sec_8k_filing(sec_client, ticker, quarter_date)
                event = _row_to_raw_event(ticker, row, fundamentals, sec_filing)
                if event is not None:
                    events.append(event)

    log.info("earnings.fetch.completed", parsed=len(events))
    return events
