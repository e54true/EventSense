"""Celery tasks for price polling — separate from event fetchers because
prices go to price_snapshots (not events) and have market-hours gating.
"""

import asyncio

import structlog

from app.adapters import prices
from app.config.settings import get_settings
from app.db.session import transient_session
from app.lib.market_hours import is_market_open
from app.services.price_writer import persist_prices
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _persist(ticks: list[prices.PriceTick]) -> int:
    async with transient_session() as db:
        return await persist_prices(db, ticks)


@celery_app.task(name="app.tasks.prices.fetch_prices_task")
def fetch_prices_task() -> dict[str, int | bool]:
    """Pull 1-minute bars for each watchlist ticker (+SPY) and persist.

    Gate on market hours inside the task (not in Beat) so we don't have to
    encode DST shifts in the cron expression. Off-hours = cheap no-op.
    """
    log = logger.bind(task="fetch_prices_task")
    log.info("task.started")

    if not is_market_open():
        log.info("task.skipped_market_closed")
        return {"market_open": False, "inserted": 0}

    tickers = get_settings().watchlist
    all_ticks: list[prices.PriceTick] = []
    for ticker in tickers:
        all_ticks.extend(prices.intraday(ticker))

    inserted = asyncio.run(_persist(all_ticks))
    log.info("task.completed", parsed=len(all_ticks), inserted=inserted, tickers=len(tickers))
    return {"market_open": True, "parsed": len(all_ticks), "inserted": inserted}
