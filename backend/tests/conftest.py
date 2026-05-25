"""Pytest fixtures shared across unit and integration tests.

Integration tests hit a real Postgres (assumed reachable at the URL in settings.database_url —
typically the same docker-compose Postgres used for dev). Each test gets a clean events
table to keep tests independent.

For CI we'll override DATABASE_URL to point at the GitHub Actions service postgres.
"""

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Yield an async session against the configured DB, truncating events before each test."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)

    async with session_local() as session:
        # TRUNCATE is faster than DELETE on a large table and resets sequences.
        # CASCADE in case future tests add child rows (predictions etc).
        await session.execute(text("TRUNCATE TABLE events CASCADE"))
        await session.commit()
        yield session

    await engine.dispose()
