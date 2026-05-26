"""Celery task wrapping the analyzer service.

Lives on its own queue (`analyze_queue`) so a slow LLM call can't starve the
fast fetcher tasks. Worker concurrency for this queue is intentionally low
(set when launching the worker) — concurrent LLM calls fight for rate limits.
"""

import asyncio

import structlog

from app.db.session import transient_session
from app.services.analyzer import analyze_pending
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _run() -> dict[str, int]:
    async with transient_session() as db:
        return await analyze_pending(db)


@celery_app.task(name="app.tasks.analyzers.analyze_pending_task")
def analyze_pending_task() -> dict[str, int]:
    log = logger.bind(task="analyze_pending_task")
    log.info("task.started")
    result = asyncio.run(_run())
    log.info("task.completed", **result)
    return result
