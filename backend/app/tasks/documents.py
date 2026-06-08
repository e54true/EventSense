"""Celery task: download 8-K filing documents for events that lack them.

Runs on a 1-minute cadence. Picks 8-K events that have no event_documents
row yet, fans out one document_fetcher run per event. The (event_id, doc_kind)
unique constraint dedups across retries.

Routed to `fetch_queue` since this is HTTP-bound, not LLM-bound.
"""

import asyncio
import uuid

import structlog
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, EventDocument, EventSource
from app.db.session import transient_session
from app.services.document_fetcher import fetch_documents_for_event
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

# How many events to process per task tick. Bounded so a backlog doesn't hold
# a worker for 30+ minutes on first deploy (one HTTP roundtrip per filing).
_BATCH_SIZE = 20


async def _candidate_event_ids(db: AsyncSession, limit: int) -> list[uuid.UUID]:
    """8-K events with no event_documents row yet, oldest-first."""
    no_docs_yet = ~exists().where(EventDocument.event_id == Event.id)
    rows = await db.scalars(
        select(Event.id)
        .where(
            Event.source == EventSource.SEC_EDGAR,
            Event.event_type == "8K_FILING",
            no_docs_yet,
        )
        .order_by(Event.published_at.asc())
        .limit(limit)
    )
    return list(rows.all())


async def _fetch_pending() -> dict[str, int]:
    """Find candidate events, fetch documents for each in its own transaction."""
    async with transient_session() as scan_db:
        candidate_ids = await _candidate_event_ids(scan_db, _BATCH_SIZE)

    total_inserted = 0
    processed = 0
    for event_id in candidate_ids:
        async with transient_session() as task_db:
            event = await task_db.scalar(select(Event).where(Event.id == event_id))
            if event is None:
                continue
            inserted = await fetch_documents_for_event(task_db, event)
            total_inserted += inserted
            processed += 1

    return {"events_processed": processed, "documents_inserted": total_inserted}


@celery_app.task(name="app.tasks.documents.fetch_8k_documents_task")
def fetch_8k_documents_task() -> dict[str, int]:
    log = logger.bind(task="fetch_8k_documents_task")
    log.info("task.started")
    result = asyncio.run(_fetch_pending())
    log.info("task.completed", **result)
    return result
