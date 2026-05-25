"""Celery tasks that wrap async fetcher adapters.

Pattern for every source:
  1. Call adapter.fetch_new() to get list[RawEvent]
  2. Hand the list to event_writer.persist() for dedup + insert

Celery itself is sync, so each task spins up a fresh event loop via asyncio.run()
to call the underlying async code.
"""

import asyncio
from typing import Any

import httpx
import structlog

from app.adapters import fomc, fred, sec_edgar
from app.db.session import transient_session
from app.schemas.raw_event import RawEvent
from app.services.event_writer import persist_events
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _fetch_and_persist(raw_events: list[RawEvent]) -> int:
    # transient_session() builds a fresh NullPool engine per call — required because
    # each Celery task runs in its own asyncio.run() loop and the FastAPI pool's
    # connections are bound to the original loop.
    async with transient_session() as db:
        return await persist_events(db, raw_events)


def _run_fetch(source_name: str, fetch_fn: Any) -> dict[str, int]:
    """Shared scaffolding: call adapter, persist, log uniformly."""
    log = logger.bind(task=f"fetch_{source_name}_task")
    log.info("task.started")
    raw_events = asyncio.run(fetch_fn())
    inserted = asyncio.run(_fetch_and_persist(raw_events))
    log.info("task.completed", parsed=len(raw_events), inserted=inserted)
    return {"parsed": len(raw_events), "inserted": inserted}


# Common Celery decorator config — every fetcher gets the same retry policy.
# autoretry_for catches transient HTTPError that tenacity (inside adapter) couldn't.
_common_task_kwargs = dict(
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)


@celery_app.task(name="app.tasks.fetchers.fetch_fred_cpi_task", **_common_task_kwargs)
def fetch_fred_cpi_task() -> dict[str, int]:
    return _run_fetch("fred_cpi", fred.fetch_new)


@celery_app.task(name="app.tasks.fetchers.fetch_sec_edgar_task", **_common_task_kwargs)
def fetch_sec_edgar_task() -> dict[str, int]:
    return _run_fetch("sec_edgar", sec_edgar.fetch_new)


@celery_app.task(name="app.tasks.fetchers.fetch_fomc_task", **_common_task_kwargs)
def fetch_fomc_task() -> dict[str, int]:
    return _run_fetch("fomc", fomc.fetch_new)
