from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings

settings = get_settings()

# --- FastAPI engine: long-lived process, real connection pool ---
#
# DECISION: pool_pre_ping catches stale connections after DB restart / network blip.
# For a low-volume app it's cheap insurance.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a pooled async session."""
    async with AsyncSessionLocal() as session:
        yield session


# --- Worker context: fresh engine per task invocation ---
#
# Celery tasks call `asyncio.run(...)` which spawns a brand new event loop each
# time. The pooled FastAPI engine above keeps asyncpg connections bound to the
# loop where they were first opened — reusing them under a different loop raises
# "got Future attached to a different loop".
#
# Fix: in worker context, build a transient engine with NullPool so every call
# does a fresh connect + disconnect. Throughput cost is trivial at our scale
# (one task per source per scheduled tick), and we sidestep the loop-binding bug.
@asynccontextmanager
async def transient_session() -> AsyncIterator[AsyncSession]:
    """Yield a session whose engine lives only for the lifetime of this `async with`.

    Use this in Celery tasks (anywhere `asyncio.run()` is the caller). Use
    `AsyncSessionLocal` / `get_db` everywhere else.
    """
    transient_engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )
    session_local = async_sessionmaker(transient_engine, expire_on_commit=False)
    try:
        async with session_local() as session:
            yield session
    finally:
        await transient_engine.dispose()
