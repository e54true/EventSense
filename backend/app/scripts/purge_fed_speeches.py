"""One-shot purge of the reverted M9.8 Fed-speeches/testimony ingestion.

M9.8 (FED_SPEECH / FED_TESTIMONY events under source=FOMC) was deployed briefly
then reverted — the addition was reasoning-driven, not data-driven. Production
ingested some of these events before the revert; they pollute /accuracy and
/pnl (the FOMC source now mixes rate statements with speeches). This deletes
them. Deleting the events cascades to their predictions and outcomes via the
ON DELETE CASCADE foreign keys (predictions.event_id, prediction_outcomes.prediction_id).

Safe by default: prints what WOULD be deleted and exits. Pass APPLY=1 to commit
the delete.

Run (dry-run):
  cd backend && DATABASE_URL=<prod> .venv/bin/python -m app.scripts.purge_fed_speeches
Run (apply):
  cd backend && APPLY=1 DATABASE_URL=<prod> .venv/bin/python -m app.scripts.purge_fed_speeches
"""

import asyncio
import os

import structlog
from sqlalchemy import text

from app.db.session import transient_session
from app.logging_config import configure_logging

logger = structlog.get_logger(__name__)

_EVENT_TYPES = ("FED_SPEECH", "FED_TESTIMONY")

# All SQL below is fully literal (no interpolation, no user input) — the target
# rows are exactly source=FOMC with these two reverted-M9.8 event types.
_COUNT_EVENTS = "SELECT count(*) FROM events WHERE source = 'FOMC' AND event_type IN ('FED_SPEECH', 'FED_TESTIMONY')"
_COUNT_PREDS = (
    "SELECT count(*) FROM predictions WHERE event_id IN "
    "(SELECT id FROM events WHERE source = 'FOMC' AND event_type IN ('FED_SPEECH', 'FED_TESTIMONY'))"
)
_COUNT_OUTCOMES = (
    "SELECT count(*) FROM prediction_outcomes WHERE prediction_id IN "
    "(SELECT id FROM predictions WHERE event_id IN "
    "(SELECT id FROM events WHERE source = 'FOMC' AND event_type IN ('FED_SPEECH', 'FED_TESTIMONY')))"
)
_DELETE_EVENTS = (
    "DELETE FROM events WHERE source = 'FOMC' AND event_type IN ('FED_SPEECH', 'FED_TESTIMONY')"
)


async def _run() -> None:
    apply = os.environ.get("APPLY") == "1"
    log = logger.bind(script="purge_fed_speeches", mode="apply" if apply else "dry-run")
    log.info("started", event_types=_EVENT_TYPES)

    async with transient_session() as db:
        # Count the blast radius before touching anything.
        n_events = (await db.execute(text(_COUNT_EVENTS))).scalar_one()
        n_preds = (await db.execute(text(_COUNT_PREDS))).scalar_one()
        n_outcomes = (await db.execute(text(_COUNT_OUTCOMES))).scalar_one()
        log.info(
            "blast_radius",
            events=n_events,
            predictions=n_preds,
            outcomes=n_outcomes,
        )

        if not apply:
            log.info("dry_run_no_changes", hint="re-run with APPLY=1 to delete")
            return

        # Delete events; ON DELETE CASCADE removes their predictions + outcomes.
        result = await db.execute(text(_DELETE_EVENTS))
        deleted = int(getattr(result, "rowcount", 0) or 0)
        await db.commit()
        log.info(
            "completed",
            events_deleted=deleted,
            predictions_cascade=n_preds,
            outcomes_cascade=n_outcomes,
        )


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
