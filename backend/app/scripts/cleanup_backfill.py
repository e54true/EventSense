"""One-shot cleanup: refresh existing earnings payloads + flip events back to FETCHED.

Why this exists:
  - Earnings events ingested before Phase A lack the `fundamentals` block.
  - Earnings events ingested before today's SEC-linkage commit lack `sec_filing`
    + `yahoo_finance_url`.
  - All events analyzed under v1 prompt before Phase 4 only have COMPANY
    predictions, never MARKET — the analyzer's state machine doesn't re-run
    ANALYZED rows, so they're stuck under v1 unless we manually flip them.

This script:
  1. For every EARNINGS_REPORT event: re-fetch yfinance income_stmt + SEC 8-K
     lookup, UPDATE the payload in place. yfinance fundamentals are derived
     per-quarter, so re-fetching produces the same numbers we'd have got at
     ingest time if Phase A had been live.
  2. For every event with status=ANALYZED: flip to FETCHED. Analyzer picks
     them up within 1 minute, re-analyzes under v2 (MARKET + COMPANY impacts,
     v2 prompt with macro context + attached documents).

Old v1 predictions are intentionally NOT deleted — they stay for
historical comparison via /accuracy?prompt_version=v1 vs v2 once we wire
that filter. The new v2 predictions sit alongside.

Run via:
  docker compose exec backend python -m app.scripts.cleanup_backfill
  # OR locally:
  cd backend && .venv/bin/python -m app.scripts.cleanup_backfill
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.earnings import (
    _build_fundamentals,
    _earnings_history_rows,
    _fetch_income_stmt_by_quarter,
    _lookup_sec_8k_filing,
)
from app.config.settings import get_settings
from app.db.models import Event, EventSource, EventStatus
from app.db.session import transient_session
from app.logging_config import configure_logging

logger = structlog.get_logger(__name__)


async def _refresh_earnings_payload(db: AsyncSession, sec_client: httpx.AsyncClient) -> int:
    """For each EARNINGS_REPORT event, recompute fundamentals + SEC link
    + Yahoo URL and UPDATE payload. Returns count updated."""
    log = logger.bind(step="refresh_earnings")
    events = (await db.scalars(select(Event).where(Event.source == EventSource.EARNINGS))).all()
    log.info("found", count=len(events))

    # Cache income_stmt per ticker so we don't re-fetch yfinance N times for N quarters.
    income_cache: dict[str, dict[Any, Any] | None] = {}
    updated = 0

    for event in events:
        if not event.affected_tickers:
            continue
        ticker = event.affected_tickers[0]

        # Confirm yfinance still has this report — should always be true since
        # earnings_history is months-deep.
        rows = _earnings_history_rows(ticker)
        target_date = event.published_at.date()
        matching_row = next((r for r in rows if r["report_date"].date() == target_date), None)
        if matching_row is None:
            log.warning(
                "no_yfinance_row_for_event",
                ticker=ticker,
                report_date=target_date.isoformat(),
            )
            continue

        if ticker not in income_cache:
            income_cache[ticker] = _fetch_income_stmt_by_quarter(ticker)
        fundamentals = _build_fundamentals(income_cache[ticker], target_date)
        sec_filing = await _lookup_sec_8k_filing(sec_client, ticker, target_date)

        # Rebuild the payload in the same shape earnings._row_to_raw_event uses.
        new_payload: dict[str, Any] = {
            "ticker": ticker,
            "report_date": target_date.isoformat(),
            "eps_actual": matching_row["eps_actual"],
            "eps_estimate": matching_row["eps_estimate"],
            "surprise_percent": matching_row["surprise_pct"],
            "yahoo_finance_url": f"https://finance.yahoo.com/quote/{ticker}/",
        }
        if fundamentals is not None:
            new_payload["fundamentals"] = fundamentals
        if sec_filing is not None:
            new_payload["sec_filing"] = sec_filing

        await db.execute(update(Event).where(Event.id == event.id).values(payload=new_payload))
        updated += 1
        log.info(
            "updated",
            ticker=ticker,
            report_date=target_date.isoformat(),
            has_fundamentals=fundamentals is not None,
            has_sec_filing=sec_filing is not None,
        )

    await db.commit()
    log.info("done", updated=updated)
    return updated


async def _flip_to_fetched(db: AsyncSession) -> int:
    """Mark every ANALYZED event back to FETCHED so the analyzer re-runs them
    under v2. Returns count updated."""
    log = logger.bind(step="flip_to_fetched")
    result = await db.execute(
        update(Event)
        .where(Event.status == EventStatus.ANALYZED)
        .values(status=EventStatus.FETCHED, failure_reason=None)
    )
    # CursorResult exposes rowcount; the generic Result base type doesn't — same
    # pattern used in price_writer.persist_prices.
    count = int(getattr(result, "rowcount", 0) or 0)
    await db.commit()
    log.info("flipped", count=count)
    return count


async def _run() -> None:
    settings = get_settings()
    log = logger.bind(script="cleanup_backfill", started_at=datetime.now(UTC).isoformat())
    log.info("started")

    sec_headers = {"User-Agent": settings.sec_user_agent}
    async with httpx.AsyncClient(
        timeout=15.0, headers=sec_headers, follow_redirects=True
    ) as sec_client:
        async with transient_session() as db:
            earnings_updated = await _refresh_earnings_payload(db, sec_client)
        async with transient_session() as db:
            flipped = await _flip_to_fetched(db)

    log.info("completed", earnings_updated=earnings_updated, events_flipped=flipped)


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
