"""Integration test: indicator_writer must dedup via ON CONFLICT DO NOTHING.

Same pattern as test_price_writer.py — bulk-insert path + re-running the same
batch inserts zero. Requires Postgres (docker compose up postgres).
"""

from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.db.models import Indicator
from app.schemas.indicator import IndicatorObservation
from app.services.indicator_writer import persist_indicators


@pytest_asyncio.fixture
async def clean_indicators_db() -> AsyncSession:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)
    async with session_local() as session:
        await session.execute(text("TRUNCATE TABLE indicators"))
        await session.commit()
        yield session
    await engine.dispose()


def _obs(key: str, day: int, value: float) -> IndicatorObservation:
    return IndicatorObservation(
        indicator_key=key,
        observed_at=datetime(2026, 6, day, tzinfo=UTC),
        value=value,
        source="FRED",
        payload={"series_id": key},
    )


async def test_persist_indicators_inserts_then_dedups(
    clean_indicators_db: AsyncSession,
) -> None:
    batch = [
        _obs("DGS10", 4, 4.28),
        _obs("DGS10", 5, 4.30),
        _obs("DGS2", 4, 4.85),
    ]
    first = await persist_indicators(clean_indicators_db, batch)
    second = await persist_indicators(clean_indicators_db, batch)

    assert first == 3
    assert second == 0
    total = await clean_indicators_db.scalar(select(func.count()).select_from(Indicator))
    assert total == 3


async def test_persist_indicators_empty_list_is_noop(
    clean_indicators_db: AsyncSession,
) -> None:
    assert await persist_indicators(clean_indicators_db, []) == 0


async def test_persist_indicators_mixed_new_and_existing(
    clean_indicators_db: AsyncSession,
) -> None:
    await persist_indicators(
        clean_indicators_db, [_obs("DGS10", 4, 4.28), _obs("DGS10", 5, 4.30)]
    )
    second_batch = [
        _obs("DGS10", 5, 4.30),  # dup
        _obs("DGS10", 6, 4.32),  # new
        _obs("DGS2", 6, 4.90),  # new (different key, same date)
    ]
    inserted = await persist_indicators(clean_indicators_db, second_batch)
    assert inserted == 2
