"""Celery task wrapping the validator service.

Validator work is IO-bound (DB reads for prices, DB writes for outcomes) with
no external API calls, so we share fetch_queue rather than spinning up a
dedicated worker. Spec §8 ideal has its own validate_queue; we route to
validate_queue but have the existing fetch worker listen to both — gives us
queue-name separation for future scaling without runtime container sprawl.
"""

import asyncio

import structlog

from app.db.session import transient_session
from app.services.validator import validate_pending
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _run() -> dict[str, int]:
    async with transient_session() as db:
        return await validate_pending(db)


@celery_app.task(name="app.tasks.validators.validate_pending_task")
def validate_pending_task() -> dict[str, int]:
    log = logger.bind(task="validate_pending_task")
    log.info("task.started")
    result = asyncio.run(_run())
    log.info("task.completed", **result)
    return result
