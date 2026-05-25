"""One-shot script: populate price_snapshots with 1 year of daily closes.

Run via:
  docker compose exec backend python -m app.scripts.backfill_prices

Idempotent — re-running just re-INSERTs (no-ops on the unique constraint).

This bootstraps the SPY baseline that the M6 validator needs for excess-return
calculations, and gives us enough history for charts on M7's event detail page.
"""

import asyncio

import structlog

from app.adapters import prices
from app.config.settings import get_settings
from app.db.session import transient_session
from app.logging_config import configure_logging
from app.services.price_writer import persist_prices

logger = structlog.get_logger(__name__)


async def _run() -> None:
    settings = get_settings()
    log = logger.bind(script="backfill_prices", tickers=len(settings.watchlist))
    log.info("backfill.started")

    all_ticks: list[prices.PriceTick] = []
    for ticker in settings.watchlist:
        ticks = prices.daily(ticker, period="1y")
        log.info("backfill.ticker.fetched", ticker=ticker, count=len(ticks))
        all_ticks.extend(ticks)

    async with transient_session() as db:
        inserted = await persist_prices(db, all_ticks)

    log.info("backfill.completed", parsed=len(all_ticks), inserted=inserted)


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
