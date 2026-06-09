"""One-shot: collapse duplicate v2 predictions to the newest per
(event_id, ticker, kind).

Background: cleanup_backfill was run twice while debugging the v3.2 prompt
pipeline. Each run added a fresh batch of v2 predictions on top of the prior
batch. Result: every event has 2 v2 predictions for the same (ticker, kind)
slot — same prompt_version label, slightly different reasoning/confidence.

This script keeps the NEWEST v2 row per (event_id, ticker, kind) and deletes
the rest. PredictionOutcome rows cascade-delete via FK ondelete=CASCADE.
v1 predictions are untouched.

Run:
  cd backend && .venv/bin/python -m app.scripts.dedupe_predictions
"""

import asyncio

import structlog
from sqlalchemy import text

from app.db.session import transient_session
from app.logging_config import configure_logging

logger = structlog.get_logger(__name__)


async def _run() -> None:
    log = logger.bind(script="dedupe_predictions")
    log.info("started")

    # ROW_NUMBER() partitions by the identity tuple, ordered by created_at DESC
    # so rn=1 is the newest survivor. Everything rn>=2 is deleted.
    delete_sql = text("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY event_id, ticker, kind
                       ORDER BY created_at DESC
                   ) AS rn
            FROM predictions
            WHERE prompt_version = :pv
        )
        DELETE FROM predictions
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
    """)

    # Count first so the log shows the impact.
    count_sql = text("""
        SELECT COUNT(*) AS n FROM (
            SELECT ROW_NUMBER() OVER (
                       PARTITION BY event_id, ticker, kind
                       ORDER BY created_at DESC
                   ) AS rn
            FROM predictions
            WHERE prompt_version = :pv
        ) ranked
        WHERE rn > 1
    """)

    async with transient_session() as db:
        result = await db.execute(count_sql, {"pv": "v2"})
        to_delete = result.scalar() or 0
        log.info("planned", to_delete=to_delete)
        if to_delete > 0:
            await db.execute(delete_sql, {"pv": "v2"})
            await db.commit()
        log.info("done", deleted=to_delete)


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
