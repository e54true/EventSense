"""Celery tasks for indicator polling.

Separate from event fetchers because indicators write to a different table
(`indicators` vs `events`) and have no FETCHED→ANALYZED downstream — they're
*state* that the analyzer reads as context.

Routed to `fetch_queue` (declared in workers/celery_app.py) — same I/O profile
as the other HTTP fetchers.
"""

import asyncio
from typing import Any

import httpx
import structlog

from app.adapters import indicators_fred
from app.db.session import transient_session
from app.schemas.indicator import IndicatorObservation
from app.services.indicator_writer import persist_indicators
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _persist(observations: list[IndicatorObservation]) -> int:
    async with transient_session() as db:
        return await persist_indicators(db, observations)


def _run_fetch(source_name: str, fetch_fn: Any) -> dict[str, int]:
    """Shared scaffolding: call adapter, persist, log uniformly. Mirrors fetchers._run_fetch."""
    log = logger.bind(task=f"fetch_{source_name}_indicators_task")
    log.info("task.started")
    observations = asyncio.run(fetch_fn())
    inserted = asyncio.run(_persist(observations))
    log.info("task.completed", parsed=len(observations), inserted=inserted)
    return {"parsed": len(observations), "inserted": inserted}


_common_task_kwargs = dict(
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)


@celery_app.task(name="app.tasks.indicators.fetch_fred_indicators_task", **_common_task_kwargs)
def fetch_fred_indicators_task() -> dict[str, int]:
    return _run_fetch("fred", indicators_fred.fetch_new)
