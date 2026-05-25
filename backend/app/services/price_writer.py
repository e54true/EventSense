"""Persist PriceTicks to the price_snapshots table.

Uses INSERT...ON CONFLICT DO NOTHING (Postgres native) instead of the
per-row try/except IntegrityError pattern that event_writer uses. Reason:
price snapshots arrive in bursts of ~14 tickers * 390 minutes = 5460 rows
per backfill batch — doing 5460 individual flushes would be ~30 seconds of
round trips. The bulk upsert is one round trip.

Also updates a Redis cache of the latest price per ticker (60s TTL) so the
GET /prices/{ticker}/latest endpoint and future LLM analyzer don't repeatedly
hit Postgres for the same hot lookup.
"""

from decimal import Decimal

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.prices import PriceTick
from app.db.models import PriceSnapshot
from app.services.price_cache import cache_latest_price

logger = structlog.get_logger(__name__)

# Cap a single insert batch to keep statement size reasonable. With ~14 tickers
# pulling 1d of 1m bars (~390 rows each) we'd otherwise build a ~5500-row VALUES
# clause — Postgres handles it but query plan logging gets ugly.
_MAX_BATCH = 1000


async def persist_prices(db: AsyncSession, ticks: list[PriceTick]) -> int:
    """Bulk insert ticks; rows that violate the unique constraint are skipped."""
    if not ticks:
        return 0

    log = logger.bind(count=len(ticks))
    log.info("price_writer.persist.started")

    inserted_total = 0
    for chunk_start in range(0, len(ticks), _MAX_BATCH):
        chunk = ticks[chunk_start : chunk_start + _MAX_BATCH]
        rows = [
            {
                "ticker": t.ticker,
                "snapshot_at": t.snapshot_at,
                "price": t.price,
                "source": "yfinance",
            }
            for t in chunk
        ]
        stmt = pg_insert(PriceSnapshot).values(rows).on_conflict_do_nothing(
            constraint="uq_price_snapshots_dedup",
        )
        result = await db.execute(stmt)
        # rowcount reflects rows actually inserted (excludes the skipped duplicates).
        inserted_total += result.rowcount or 0

    await db.commit()

    # Refresh the latest-price cache from this batch — pick the freshest tick per ticker.
    latest_per_ticker: dict[str, PriceTick] = {}
    for t in ticks:
        existing = latest_per_ticker.get(t.ticker)
        if existing is None or t.snapshot_at > existing.snapshot_at:
            latest_per_ticker[t.ticker] = t
    for ticker, tick in latest_per_ticker.items():
        await cache_latest_price(ticker, tick.price)

    log.info("price_writer.persist.completed", inserted=inserted_total)
    return inserted_total


def latest_per_ticker(ticks: list[PriceTick]) -> dict[str, Decimal]:
    """Helper for the backfill script — pick newest price per ticker from a batch."""
    out: dict[str, tuple[PriceTick, Decimal]] = {}
    for t in ticks:
        prev = out.get(t.ticker)
        if prev is None or t.snapshot_at > prev[0].snapshot_at:
            out[t.ticker] = (t, t.price)
    return {ticker: price for ticker, (_, price) in out.items()}
