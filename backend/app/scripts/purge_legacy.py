"""One-shot purge of legacy artifacts after the alignment semantics change.

Deletes:
  - ALL v1 predictions (cascade-deletes their outcomes via FK).
  - ALL v2 prediction_outcomes (forces production validator to recompute
    aligned under the new raw_return-only semantics).

Keeps:
  - events, indicators, event_documents — externally-sourced + dedup'd, correct.
  - v2 predictions — already cleaned of duplicates and produced under the
    final v3.2 prompt. Re-validating them is cheap.

After running, production validator (every 5 min) refills v2 outcomes
within 1-2 ticks using `is_aligned(direction, raw_return)` — no more
excess-vs-SPY comparison.

Run:
  cd backend && .venv/bin/python -m app.scripts.purge_legacy
"""

import asyncio

import structlog
from sqlalchemy import text

from app.db.session import transient_session
from app.logging_config import configure_logging

logger = structlog.get_logger(__name__)


async def _run() -> None:
    log = logger.bind(script="purge_legacy")
    log.info("started")

    async with transient_session() as db:
        # 1. Delete v1 predictions. ON DELETE CASCADE on prediction_outcomes.prediction_id
        #    means their outcomes go with them — no separate v1 outcome cleanup needed.
        result = await db.execute(
            text("DELETE FROM predictions WHERE prompt_version = :pv"),
            {"pv": "v1"},
        )
        v1_preds_deleted = int(getattr(result, "rowcount", 0) or 0)
        log.info("v1_predictions_deleted", count=v1_preds_deleted)

        # 2. Delete v2 outcomes only. Predictions themselves stay; validator will
        #    re-fill outcomes under new alignment semantics.
        result = await db.execute(
            text(
                """
                DELETE FROM prediction_outcomes
                WHERE prediction_id IN (
                    SELECT id FROM predictions WHERE prompt_version = :pv
                )
                """
            ),
            {"pv": "v2"},
        )
        v2_outcomes_deleted = int(getattr(result, "rowcount", 0) or 0)
        log.info("v2_outcomes_deleted", count=v2_outcomes_deleted)

        await db.commit()

    log.info(
        "completed",
        v1_predictions_deleted=v1_preds_deleted,
        v2_outcomes_deleted=v2_outcomes_deleted,
    )


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
