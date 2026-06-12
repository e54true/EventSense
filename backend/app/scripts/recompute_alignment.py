"""One-shot in-place recompute of `aligned` after the scoring-rule change.

The per-window neutral bands (24h ±0.5%, 7d ±1.5%) and per-window directions
(direction_7d) changed how `aligned` is decided. Existing outcome rows carry
labels computed under the old flat-0.5% rule — but they also carry
ticker_return, so we can re-derive aligned without touching prices or
re-running the validator.

Idempotent: re-running converges to the same labels. Only rows whose label
actually flips get UPDATEd.

Run:
  cd backend && .venv/bin/python -m app.scripts.recompute_alignment
"""

import asyncio

import structlog
from sqlalchemy import select

from app.db.models import OutcomeWindow, Prediction, PredictionOutcome
from app.db.session import transient_session
from app.logging_config import configure_logging
from app.services import alignment

logger = structlog.get_logger(__name__)


async def _run() -> None:
    log = logger.bind(script="recompute_alignment")
    log.info("started")

    async with transient_session() as db:
        rows = (
            await db.execute(
                select(
                    PredictionOutcome,
                    Prediction.direction,
                    Prediction.direction_7d,
                ).join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
            )
        ).all()

        checked = 0
        flipped = 0
        for outcome, direction, direction_7d in rows:
            checked += 1
            if outcome.window == OutcomeWindow.D7 and direction_7d is not None:
                effective = direction_7d
            else:
                effective = direction
            new_aligned = alignment.is_aligned(effective, outcome.ticker_return, outcome.window)
            if new_aligned != outcome.aligned:
                outcome.aligned = new_aligned
                flipped += 1

        await db.commit()
        log.info("completed", checked=checked, flipped=flipped)


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
