"""One-shot purge of FRED events after the release-date anchoring fix.

Why a purge (not an update): pre-fix FRED events anchored published_at on the
observation's REFERENCE PERIOD (May CPI → May 1) instead of the actual release
date (mid-June). Every downstream artifact — predictions' predicted_at, the
validator's outcome windows, the aligned labels — measured market reaction on
the wrong days. None of it is salvageable, and the (source, external_id)
dedup constraint would block corrected rows from being re-inserted.

Deletes:
  - ALL events WHERE source = 'FRED'. FK ON DELETE CASCADE takes their
    predictions, prediction_outcomes, and event_documents with them.

Keeps:
  - SEC / FOMC / EARNINGS events — their anchors were correct.
  - indicators, price_snapshots — source-of-truth tables, unaffected.

After running: the FRED fetcher's next tick re-ingests the series in vintage
mode (true release dates + derived MoM/YoY metrics), the analyzer re-analyzes
them as fresh FETCHED events, and the validator fills outcomes once windows
mature (immediately, for historical releases whose windows already passed).

Run:
  cd backend && .venv/bin/python -m app.scripts.reset_fred
"""

import asyncio

import structlog
from sqlalchemy import text

from app.db.session import transient_session
from app.logging_config import configure_logging

logger = structlog.get_logger(__name__)


async def _run() -> None:
    log = logger.bind(script="reset_fred")
    log.info("started")

    async with transient_session() as db:
        counts = (
            await db.execute(
                text(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM events WHERE source = 'FRED') AS events,
                        (SELECT COUNT(*) FROM predictions p
                            JOIN events e ON e.id = p.event_id
                            WHERE e.source = 'FRED') AS predictions,
                        (SELECT COUNT(*) FROM prediction_outcomes o
                            JOIN predictions p ON p.id = o.prediction_id
                            JOIN events e ON e.id = p.event_id
                            WHERE e.source = 'FRED') AS outcomes
                    """
                )
            )
        ).one()
        log.info(
            "about_to_delete",
            events=counts.events,
            predictions=counts.predictions,
            outcomes=counts.outcomes,
        )

        result = await db.execute(text("DELETE FROM events WHERE source = 'FRED'"))
        deleted = int(getattr(result, "rowcount", 0) or 0)
        await db.commit()
        log.info("completed", events_deleted=deleted)


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
