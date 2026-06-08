"""Integration test for context_builder: recent-events window + indicator
freshest-value lookup + 30d delta. Hits a real Postgres."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.db.models import Event, EventSource, EventStatus, Indicator
from app.services.context_builder import build_context

_TRIGGER_AT = datetime(2026, 6, 1, 14, 30, tzinfo=UTC)


@pytest_asyncio.fixture
async def clean_db() -> AsyncSession:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)
    async with session_local() as session:
        await session.execute(text("TRUNCATE TABLE events CASCADE"))
        await session.execute(text("TRUNCATE TABLE indicators"))
        await session.commit()
        yield session
    await engine.dispose()


async def _seed_event(
    db: AsyncSession,
    *,
    external_id: str,
    published_at: datetime,
    event_type: str = "8K_FILING",
    source: EventSource = EventSource.SEC_EDGAR,
) -> Event:
    e = Event(
        source=source,
        event_type=event_type,
        external_id=external_id,
        title=f"event {external_id}",
        payload={"k": "v"},
        affected_tickers=["NVDA"],
        published_at=published_at,
        fetched_at=published_at,
        status=EventStatus.FETCHED,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _seed_indicator(
    db: AsyncSession, *, key: str, observed_at: datetime, value: float
) -> None:
    db.add(
        Indicator(
            indicator_key=key,
            observed_at=observed_at,
            value=Decimal(str(value)),
            source="FRED",
            payload={},
        )
    )
    await db.commit()


async def test_context_includes_only_events_in_lookback_window(
    clean_db: AsyncSession,
) -> None:
    trigger = await _seed_event(
        clean_db, external_id="trigger", published_at=_TRIGGER_AT
    )
    # Inside the 30-day window
    await _seed_event(
        clean_db, external_id="recent", published_at=_TRIGGER_AT - timedelta(days=5)
    )
    # Outside the window (> 30 days ago)
    await _seed_event(
        clean_db, external_id="ancient", published_at=_TRIGGER_AT - timedelta(days=45)
    )

    ctx = await build_context(
        clean_db,
        trigger,
        lookback_days=30,
        recent_events_cap=50,
        watchlist=["NVDA", "SPY"],
    )

    titles = {e.title for e in ctx.recent_events}
    assert "event recent" in titles
    assert "event ancient" not in titles
    assert "event trigger" not in titles  # triggering event itself excluded


async def test_context_indicator_snapshot_picks_freshest_at_or_before_trigger(
    clean_db: AsyncSession,
) -> None:
    trigger = await _seed_event(
        clean_db, external_id="trigger", published_at=_TRIGGER_AT
    )
    # Older value
    await _seed_indicator(clean_db, key="DGS10", observed_at=_TRIGGER_AT - timedelta(days=35), value=4.10)
    # 30 days earlier (for delta)
    await _seed_indicator(clean_db, key="DGS10", observed_at=_TRIGGER_AT - timedelta(days=30), value=4.25)
    # Latest value within window
    await _seed_indicator(clean_db, key="DGS10", observed_at=_TRIGGER_AT - timedelta(days=1), value=4.50)
    # Future value (after trigger) — should be ignored
    await _seed_indicator(clean_db, key="DGS10", observed_at=_TRIGGER_AT + timedelta(days=1), value=9.99)

    ctx = await build_context(
        clean_db,
        trigger,
        lookback_days=30,
        recent_events_cap=50,
        watchlist=["NVDA"],
    )

    snap = ctx.latest_indicators["DGS10"]
    assert snap.value == 4.50  # freshest at-or-before trigger
    assert snap.value_30d_ago == 4.25  # the t-30d snapshot
    assert snap.delta_30d == pytest.approx(0.25)


async def test_context_indicator_without_prior_window_value_returns_none_delta(
    clean_db: AsyncSession,
) -> None:
    trigger = await _seed_event(
        clean_db, external_id="trigger", published_at=_TRIGGER_AT
    )
    # Only one observation — no prior available for delta
    await _seed_indicator(clean_db, key="SP500_PE", observed_at=_TRIGGER_AT - timedelta(days=1), value=31.83)

    ctx = await build_context(
        clean_db,
        trigger,
        lookback_days=30,
        recent_events_cap=50,
        watchlist=["NVDA"],
    )

    snap = ctx.latest_indicators["SP500_PE"]
    assert snap.value == 31.83
    assert snap.value_30d_ago is None
    assert snap.delta_30d is None


async def test_context_respects_recent_events_cap(clean_db: AsyncSession) -> None:
    """If cap=3, only 3 newest events show up."""
    trigger = await _seed_event(
        clean_db, external_id="trigger", published_at=_TRIGGER_AT
    )
    for i in range(10):
        await _seed_event(
            clean_db,
            external_id=f"r{i}",
            published_at=_TRIGGER_AT - timedelta(days=i + 1),
        )

    ctx = await build_context(
        clean_db,
        trigger,
        lookback_days=30,
        recent_events_cap=3,
        watchlist=["NVDA"],
    )
    assert len(ctx.recent_events) == 3
    # Newest first by published_at DESC
    assert ctx.recent_events[0].title == "event r0"
