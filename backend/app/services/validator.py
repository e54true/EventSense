"""Validator: turns a Prediction into a PredictionOutcome once enough time has passed.

For each prediction we eventually want three outcomes: +1h, +24h, +7d. The
validator polls for "predictions where window W is due but no outcome row
exists yet" and computes the outcome.

Why polling, not Celery ETA:
  Celery ETA-scheduled tasks live in the broker. Broker restart, worker pool
  changes, or task name renames all silently lose them. DB-driven polling is
  recoverable — the source of truth is `predictions.predicted_at` plus the
  existence (or not) of an outcome row. Restart anything; nothing is lost.

Concurrency: same queue-table pattern as the analyzer (FOR UPDATE SKIP LOCKED
inside a per-prediction transaction). Multiple validator workers safe.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    OutcomeWindow,
    Prediction,
    PredictionOutcome,
    PriceSnapshot,
)
from app.db.session import transient_session
from app.services import alignment

logger = structlog.get_logger(__name__)

# SPY is the market baseline for excess-return computation.
BENCHMARK_TICKER = "SPY"

# A small buffer past the window end to wait for prices to be available
# (price worker is on a 5-min cadence; this avoids racing it).
_PRICE_AVAILABILITY_BUFFER = timedelta(minutes=15)

# Map enum value → real-world duration.
_WINDOW_DURATIONS: dict[OutcomeWindow, timedelta] = {
    OutcomeWindow.H1: timedelta(hours=1),
    OutcomeWindow.H24: timedelta(hours=24),
    OutcomeWindow.D7: timedelta(days=7),
}

# How far back from the target timestamp we'll accept a price snapshot.
# We don't want to grab a 3-day-old close as "the 1h price" — that would
# generate misleading outcomes.
_PRICE_LOOKBACK_TOLERANCE: dict[OutcomeWindow, timedelta] = {
    OutcomeWindow.H1: timedelta(hours=1),  # tight: intraday only
    OutcomeWindow.H24: timedelta(hours=24),  # next day's daily close is fine
    OutcomeWindow.D7: timedelta(days=4),  # weekend gap allowed
}


async def _price_at_or_before(
    db: AsyncSession,
    ticker: str,
    target_at: datetime,
    tolerance: timedelta,
    *,
    must_be_after: datetime | None = None,
) -> Decimal | None:
    """Most recent price for `ticker` at or before `target_at`, within `tolerance`.

    `must_be_after`: if set, snapshot must also be strictly after this timestamp.
    This is the safety rail for the end-of-window lookup — without it, when only
    a baseline snapshot exists, the same row would satisfy both "baseline" and
    "end", silently producing a 0% return outcome that looks valid but isn't.

    Returns None if no snapshot meets the constraints — the validator will defer
    rather than write a misleading outcome.
    """
    earliest = target_at - tolerance
    stmt = (
        select(PriceSnapshot.price)
        .where(
            PriceSnapshot.ticker == ticker,
            PriceSnapshot.snapshot_at <= target_at,
            PriceSnapshot.snapshot_at >= earliest,
        )
        .order_by(PriceSnapshot.snapshot_at.desc())
        .limit(1)
    )
    if must_be_after is not None:
        stmt = stmt.where(PriceSnapshot.snapshot_at > must_be_after)
    result: Decimal | None = await db.scalar(stmt)
    return result


async def _candidate_pairs(
    db: AsyncSession,
    now: datetime,
    limit: int,
) -> list[tuple[Prediction, OutcomeWindow]]:
    """Find (prediction, window) pairs that are due for validation and not yet outcome'd.

    A pair is "due" when:
        now() >= predicted_at + window_duration + price_availability_buffer
    A pair is "not yet outcome'd" when the corresponding row in
    prediction_outcomes doesn't exist.
    """
    pairs: list[tuple[Prediction, OutcomeWindow]] = []
    for window, duration in _WINDOW_DURATIONS.items():
        cutoff = now - duration - _PRICE_AVAILABILITY_BUFFER
        no_outcome_yet = ~exists().where(
            and_(
                PredictionOutcome.prediction_id == Prediction.id,
                PredictionOutcome.window == window,
            )
        )
        rows = (
            await db.scalars(
                select(Prediction)
                .where(Prediction.predicted_at <= cutoff)
                .where(no_outcome_yet)
                .order_by(Prediction.predicted_at.asc())
                .limit(limit)
            )
        ).all()
        for p in rows:
            pairs.append((p, window))
        # Stop accumulating once we have enough — keep batches bounded.
        if len(pairs) >= limit:
            return pairs[:limit]
    return pairs


async def _build_outcome(
    db: AsyncSession,
    prediction: Prediction,
    window: OutcomeWindow,
) -> PredictionOutcome | None:
    """Compute an outcome for one (prediction, window). Returns None if prices not available yet."""
    target_at = prediction.predicted_at + _WINDOW_DURATIONS[window]
    tolerance = _PRICE_LOOKBACK_TOLERANCE[window]

    baseline_ticker = await _price_at_or_before(
        db, prediction.ticker, prediction.predicted_at, tolerance
    )
    end_ticker = await _price_at_or_before(
        db,
        prediction.ticker,
        target_at,
        tolerance,
        must_be_after=prediction.predicted_at,
    )
    baseline_spy = await _price_at_or_before(
        db, BENCHMARK_TICKER, prediction.predicted_at, tolerance
    )
    end_spy = await _price_at_or_before(
        db,
        BENCHMARK_TICKER,
        target_at,
        tolerance,
        must_be_after=prediction.predicted_at,
    )

    # Narrow the four Optional[Decimal]s explicitly so mypy can see they're
    # non-None below. `all([...])` doesn't refine variable types.
    if baseline_ticker is None or end_ticker is None or baseline_spy is None or end_spy is None:
        # Some price missing — defer. Next validator tick will retry once
        # prices arrive (typically the price-fetch worker catches up within
        # 5 minutes during market hours; backfill covers historical gaps).
        return None

    ticker_ret = alignment.ticker_return(float(baseline_ticker), float(end_ticker))
    spy_ret = alignment.ticker_return(float(baseline_spy), float(end_spy))
    excess = alignment.excess_return(ticker_ret, spy_ret)
    # Thread kind + raw_return so MARKET predictions (especially SPY-vs-SPY)
    # align on the raw market move, not the definitionally-zero excess.
    aligned = alignment.is_aligned(
        prediction.direction,
        excess,
        kind=prediction.kind,
        raw_return=ticker_ret,
    )

    return PredictionOutcome(
        prediction_id=prediction.id,
        window=window,
        baseline_price=baseline_ticker,
        end_price=end_ticker,
        ticker_return=ticker_ret,
        spy_return=spy_ret,
        excess_return=excess,
        aligned=aligned,
        validated_at=datetime.now(UTC),
    )


async def validate_pending(db: AsyncSession, batch_size: int = 50) -> dict[str, int]:
    """Find pending (prediction, window) pairs and produce outcome rows for them.

    `db` is used only for the cheap discovery query. Each outcome is written in
    its own short transaction with FOR UPDATE SKIP LOCKED — same queue-table
    pattern as the analyzer, safe under worker concurrency > 1.
    """
    now = datetime.now(UTC)
    log = logger.bind(batch_size=batch_size, now=now.isoformat())
    log.info("validator.batch.started")

    candidates = await _candidate_pairs(db, now, batch_size)

    written = 0
    deferred = 0
    skipped_locked = 0

    for prediction, window in candidates:
        async with transient_session() as task_db:
            # Lock just this prediction; verify outcome STILL doesn't exist
            # (another worker may have inserted it since our discovery query).
            locked = await task_db.scalar(
                select(Prediction)
                .where(Prediction.id == prediction.id)
                .with_for_update(skip_locked=True)
            )
            if locked is None:
                skipped_locked += 1
                continue

            already_done = await task_db.scalar(
                select(PredictionOutcome.id).where(
                    PredictionOutcome.prediction_id == prediction.id,
                    PredictionOutcome.window == window,
                )
            )
            if already_done is not None:
                continue

            outcome = await _build_outcome(task_db, locked, window)
            if outcome is None:
                deferred += 1
                continue

            task_db.add(outcome)
            await task_db.commit()
            written += 1

    log.info(
        "validator.batch.completed",
        written=written,
        deferred=deferred,
        skipped_locked=skipped_locked,
        candidates=len(candidates),
    )
    return {
        "outcomes_written": written,
        "deferred_no_price": deferred,
        "skipped_locked": skipped_locked,
        "candidates": len(candidates),
    }
