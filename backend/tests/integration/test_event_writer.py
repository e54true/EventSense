"""Integration test: event_writer must dedup across all sources.

Verifies the shared writer (used by FRED, SEC, FOMC tasks) is idempotent and
handles RawEvents from any source correctly.

Requires a running Postgres (docker compose up postgres).
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, EventSource
from app.schemas.raw_event import RawEvent
from app.services.event_writer import persist_events


def _raw(source: EventSource, external_id: str, title: str = "x") -> RawEvent:
    return RawEvent(
        source=source,
        event_type="TEST",
        external_id=external_id,
        title=title,
        payload={"k": "v"},
        affected_tickers=[],
        published_at=datetime.now(UTC),
    )


async def test_persist_inserts_then_dedups(db_session: AsyncSession) -> None:
    batch = [
        _raw(EventSource.FRED, "CPIAUCSL:2026-04-01"),
        _raw(EventSource.SEC_EDGAR, "0000320193-26-000042"),
        _raw(EventSource.FOMC, "https://www.federalreserve.gov/x.htm"),
    ]
    first = await persist_events(db_session, batch)
    second = await persist_events(db_session, batch)  # same data again

    assert first == 3
    assert second == 0
    total = await db_session.scalar(select(func.count()).select_from(Event))
    assert total == 3


async def test_persist_treats_same_external_id_different_source_as_distinct(
    db_session: AsyncSession,
) -> None:
    """The unique constraint is on (source, external_id), not external_id alone —
    so the same external_id under two different sources is two separate events.
    """
    batch = [
        _raw(EventSource.FRED, "shared-id"),
        _raw(EventSource.SEC_EDGAR, "shared-id"),
    ]
    inserted = await persist_events(db_session, batch)
    assert inserted == 2


async def test_persist_empty_list_is_noop(db_session: AsyncSession) -> None:
    assert await persist_events(db_session, []) == 0
