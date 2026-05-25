"""Price-related read endpoints.

For now: a single GET /prices/{ticker}/latest that returns the most recent
cached price. Cache fills from the price-fetcher worker; this endpoint never
hits yfinance directly (deliberately — yfinance latency is too unpredictable
for a request-path call).
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.models import PriceSnapshot
from app.db.session import get_db
from app.services.price_cache import get_latest_price

router = APIRouter(prefix="/prices", tags=["prices"])


class LatestPrice(BaseModel):
    ticker: str
    price: Decimal
    source: str  # 'cache' or 'db' — useful for debugging cache misses


@router.get("/{ticker}/latest", response_model=LatestPrice)
async def latest_price(
    ticker: str,
    db: AsyncSession = Depends(get_db),
) -> LatestPrice:
    """Return the latest known price for `ticker`.

    Flow: check Redis cache first; if miss, fall back to the latest row in
    price_snapshots. If neither has anything, 404.
    """
    ticker = ticker.upper()
    if ticker not in get_settings().watchlist:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} not in watchlist")

    cached = await get_latest_price(ticker)
    if cached is not None:
        return LatestPrice(ticker=ticker, price=cached, source="cache")

    # Cache miss — fall back to DB. Order by snapshot_at DESC + LIMIT 1 uses the
    # ix_price_snapshots_ticker_time index, so this is O(log n).
    row = await db.scalar(
        select(PriceSnapshot)
        .where(PriceSnapshot.ticker == ticker)
        .order_by(PriceSnapshot.snapshot_at.desc())
        .limit(1)
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No price data for {ticker} yet (run backfill or wait for market hours)",
        )
    return LatestPrice(ticker=ticker, price=row.price, source="db")
