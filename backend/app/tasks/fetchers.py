"""Celery tasks that wrap async fetcher adapters.

Celery itself is sync, so each task spins up a fresh event loop via asyncio.run()
to call the underlying async adapter. This is the canonical pattern when you don't
want to pull in celery-pool-asyncio or restructure adapters as sync.

Trade-off: one event loop per task invocation has non-zero overhead, but at our
scale (one task per hour per source) it's negligible. If task volume grows 100x,
revisit with celery-asyncio-pool or split into worker types.
"""

import asyncio
from typing import Any

import httpx
import structlog

from app.adapters.fred import fetch_cpi
from app.db.session import AsyncSessionLocal
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _run_fetch_cpi() -> int:
    async with AsyncSessionLocal() as db:
        return await fetch_cpi(db)


@celery_app.task(
    name="app.tasks.fetchers.fetch_fred_cpi_task",
    # Celery-level retry: catches transient HTTP errors that survive tenacity's inner
    # retry (e.g. FRED is down for >30s). Network blips inside a single fetch are
    # handled by tenacity inside the adapter itself.
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=True,
    retry_backoff_max=600,  # cap at 10 min
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def fetch_fred_cpi_task() -> dict[str, Any]:
    """Hourly task: fetch latest FRED CPI observations and store new ones."""
    log = logger.bind(task="fetch_fred_cpi_task")
    log.info("task.started")
    inserted = asyncio.run(_run_fetch_cpi())
    log.info("task.completed", inserted=inserted)
    return {"inserted": inserted}
