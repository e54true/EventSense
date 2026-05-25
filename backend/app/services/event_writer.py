"""Shared persistence for RawEvents produced by any adapter.

This is the *only* place that knows how to INSERT into the events table. By
centralizing the writer:
  - Adapters stay pure (no DB session, easier to unit test)
  - Dedup logic lives in one place (pre-check SELECT + catch IntegrityError)
  - Future cross-cutting concerns (metrics, audit log) hook in here

All callers are Celery tasks; they own the AsyncSession lifecycle and pass it in.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, EventStatus
from app.schemas.raw_event import RawEvent

logger = structlog.get_logger(__name__)


async def persist_events(db: AsyncSession, raw_events: list[RawEvent]) -> int:
    """Insert each RawEvent that isn't already present. Returns count inserted.

    Idempotent: the (source, external_id) unique constraint is the safety net.
    The pre-check SELECT is just a performance optimization to skip the round-trip
    of attempting INSERTs that we already know will collide.
    """
    if not raw_events:
        return 0

    log = logger.bind(source=raw_events[0].source.value, count=len(raw_events))
    log.info("writer.persist.started")

    inserted = 0
    now = datetime.now(UTC)

    for raw in raw_events:
        existing = await db.scalar(
            select(Event.id).where(
                Event.source == raw.source,
                Event.external_id == raw.external_id,
            )
        )
        if existing is not None:
            continue

        event = Event(
            source=raw.source,
            event_type=raw.event_type,
            external_id=raw.external_id,
            title=raw.title,
            payload=raw.payload,
            affected_tickers=list(raw.affected_tickers),
            published_at=raw.published_at,
            fetched_at=now,
            status=EventStatus.FETCHED,
        )
        db.add(event)
        try:
            await db.flush()
        except IntegrityError:
            # Race: another worker inserted the same (source, external_id) between
            # our SELECT and flush. Unique constraint did its job — move on.
            await db.rollback()
            continue
        inserted += 1

    await db.commit()
    log.info("writer.persist.completed", inserted=inserted)
    return inserted
