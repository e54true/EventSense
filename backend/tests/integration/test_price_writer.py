"""Integration test: price_writer must dedup via ON CONFLICT DO NOTHING.

Verifies bulk-insert path and that re-running the same batch inserts zero.
Requires Postgres (docker compose up postgres).
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.prices import PriceTick
from app.config.settings import get_settings
from app.db.models import PriceSnapshot
from app.services.price_writer import persist_prices


@pytest_asyncio.fixture
async def clean_prices_db() -> AsyncSession:
    """Separate fixture from db_session — that one truncates events, this one prices."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)
    async with session_local() as session:
        await session.execute(text("TRUNCATE TABLE price_snapshots"))
        await session.commit()
        yield session
    await engine.dispose()


def _tick(ticker: str, minute: int, price: str) -> PriceTick:
    return PriceTick(
        ticker=ticker,
        snapshot_at=datetime(2026, 5, 1, 14, minute, tzinfo=UTC),
        price=Decimal(price),
    )


async def test_persist_prices_inserts_then_dedups(clean_prices_db: AsyncSession) -> None:
    batch = [
        _tick("AAPL", 30, "180.5000"),
        _tick("AAPL", 31, "180.6500"),
        _tick("MSFT", 30, "420.1200"),
    ]
    first = await persist_prices(clean_prices_db, batch)
    second = await persist_prices(clean_prices_db, batch)

    assert first == 3
    assert second == 0
    total = await clean_prices_db.scalar(select(func.count()).select_from(PriceSnapshot))
    assert total == 3


async def test_persist_prices_empty_list_is_noop(clean_prices_db: AsyncSession) -> None:
    assert await persist_prices(clean_prices_db, []) == 0


async def test_persist_prices_mixed_new_and_existing(clean_prices_db: AsyncSession) -> None:
    """Inserting a batch where half is new and half already exists: only the new half inserts."""
    initial = [_tick("AAPL", 30, "180.50"), _tick("AAPL", 31, "180.65")]
    await persist_prices(clean_prices_db, initial)

    second_batch = [
        _tick("AAPL", 31, "180.65"),  # dup
        _tick("AAPL", 32, "180.80"),  # new
        _tick("AAPL", 33, "180.95"),  # new
    ]
    inserted = await persist_prices(clean_prices_db, second_batch)
    assert inserted == 2
