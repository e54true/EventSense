"""Price-related read endpoints.

For now: a single GET /prices/{ticker}/latest that returns the most recent
cached price. Cache fills from the price-fetcher worker; this endpoint never
hits yfinance directly (deliberately — yfinance latency is too unpredictable
for a request-path call).
"""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
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


class PricePoint(BaseModel):
    snapshot_at: datetime
    price: Decimal


class PriceRangeResponse(BaseModel):
    ticker: str
    points: list[PricePoint]
    # Echo of inputs — helps frontend cache keys + sanity check
    from_at: datetime
    to_at: datetime


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


@router.get("/{ticker}/range", response_model=PriceRangeResponse)
async def price_range(
    ticker: str,
    from_at: datetime = Query(..., description="ISO timestamp lower bound (inclusive)"),
    to_at: datetime = Query(..., description="ISO timestamp upper bound (inclusive)"),
    db: AsyncSession = Depends(get_db),
) -> PriceRangeResponse:
    """All snapshots for `ticker` between `from_at` and `to_at`, ascending.

    Used by the event-detail chart on the frontend. We cap the range to keep
    payloads bounded (`to_at - from_at` must be <= 30 days for now).
    """
    ticker = ticker.upper()
    if ticker not in get_settings().watchlist:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} not in watchlist")
    if to_at <= from_at:
        raise HTTPException(status_code=400, detail="to_at must be after from_at")
    if (to_at - from_at).days > 30:
        raise HTTPException(status_code=400, detail="Range too wide (max 30 days)")

    rows = (
        await db.scalars(
            select(PriceSnapshot)
            .where(
                PriceSnapshot.ticker == ticker,
                PriceSnapshot.snapshot_at >= from_at,
                PriceSnapshot.snapshot_at <= to_at,
            )
            .order_by(PriceSnapshot.snapshot_at.asc())
        )
    ).all()

    return PriceRangeResponse(
        ticker=ticker,
        from_at=from_at,
        to_at=to_at,
        points=[PricePoint(snapshot_at=r.snapshot_at, price=r.price) for r in rows],
    )
