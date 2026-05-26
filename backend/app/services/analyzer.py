"""Analyzer: turn FETCHED events into predictions via an LLM call.

State machine (per spec §8):
    FETCHED → (LLM call) → ANALYZED        (success path)
    FETCHED → (LLM call) → FAILED          (any unrecoverable error)

Each event spawns N predictions (one per ticker the LLM thinks is impacted).
A FAILED event is left with failure_reason so an operator can inspect why and
either fix the prompt or mark it IGNORED.

Concurrency model — queue-table pattern:
  1. Pick up candidate event IDs (FETCHED, oldest first).
  2. For each ID, open a fresh transaction, try to lock the row with
     SELECT ... FOR UPDATE SKIP LOCKED. If another analyzer worker already
     holds the lock, the SELECT returns None and we move on.
  3. Process within that short transaction; commit releases the lock and
     transitions the event to ANALYZED or FAILED.

This pattern lets us safely run multiple analyzer workers (or accept Beat
ticks that overlap with in-flight tasks) without double-processing.

Idempotency guarantee: only process rows WHERE status = FETCHED. Once moved
to ANALYZED or FAILED, future polls won't pick the event up again.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.models import Event, EventStatus, Prediction
from app.db.session import transient_session
from app.llm import clients
from app.llm.cost import estimate_cost_usd, today_spend_usd
from app.llm.router import choose_model
from app.llm.schemas import EventAnalysis

logger = structlog.get_logger(__name__)


async def _process_one(db: AsyncSession, event: Event, spend_today: float) -> int:
    """Run LLM on `event`, write predictions, transition status. Returns predictions emitted.

    The caller owns the transaction; this function does NOT commit. The caller
    commits after this returns (success or failure path).
    """
    log = logger.bind(event_id=str(event.id), source=event.source.value)
    choice = choose_model(event.source, event.event_type, spend_today)
    watchlist = get_settings().watchlist
    prompt = clients.build_prompt(event.payload, watchlist)

    try:
        result = await clients.analyze_event(choice, prompt)
    except Exception as exc:
        log.warning("analyzer.llm_failed", error=str(exc), error_type=type(exc).__name__)
        event.status = EventStatus.FAILED
        event.failure_reason = f"LLM call failed: {type(exc).__name__}: {exc}"[:1000]
        return 0

    cost = estimate_cost_usd(choice.model, result.prompt_tokens, result.completion_tokens)
    predictions = _build_predictions(event, result.analysis, choice, cost)
    db.add_all(predictions)
    event.status = EventStatus.ANALYZED
    event.failure_reason = None

    log.info(
        "analyzer.event_done",
        predictions=len(predictions),
        model=choice.model,
        cost_usd=round(cost, 6),
    )
    return len(predictions)


def _build_predictions(
    event: Event,
    analysis: EventAnalysis,
    choice: clients.ModelChoice,  # type: ignore[attr-defined]
    cost_usd: float,
) -> list[Prediction]:
    """Turn one EventAnalysis into N Prediction ORM rows.

    Cost is attributed only to the first prediction — sum-by-day still gives the
    right total, and per-prediction division would create misleading fractions.
    """
    now = datetime.now(UTC)
    rows: list[Prediction] = []
    for i, impact in enumerate(analysis.impacts):
        # Skip tickers the LLM hallucinated outside the watchlist. instructor's
        # validation only constrains string shape, not values.
        if impact.ticker not in get_settings().watchlist:
            logger.warning(
                "analyzer.hallucinated_ticker",
                event_id=str(event.id),
                ticker=impact.ticker,
            )
            continue
        rows.append(
            Prediction(
                event_id=event.id,
                ticker=impact.ticker,
                direction=impact.direction,
                magnitude=impact.magnitude,
                confidence=impact.confidence,
                reasoning=impact.reasoning,
                llm_provider=choice.provider,
                llm_model=choice.model,
                prompt_version=clients.PROMPT_VERSION,
                llm_cost_usd=cost_usd if i == 0 else 0.0,
                predicted_at=now,
            )
        )
    return rows


async def _candidate_event_ids(db: AsyncSession, limit: int) -> list:
    """Cheap read-only query: which events look pending? Lock comes later, per event."""
    result = await db.scalars(
        select(Event.id)
        .where(Event.status == EventStatus.FETCHED)
        .order_by(Event.published_at.asc())
        .limit(limit)
    )
    return list(result.all())


async def analyze_pending(db: AsyncSession, batch_size: int | None = None) -> dict[str, int]:
    """Pick up FETCHED events and run them through the LLM.

    `db` is used only for the initial candidate scan and spend lookup. Each event
    is processed in its OWN transient session/transaction so the row-level
    FOR UPDATE SKIP LOCKED lock has a meaningful scope (released on per-event
    commit, not at the end of the whole batch).

    This makes the analyzer safe to run with worker concurrency > 1, multiple
    analyzer containers, or overlapping Beat ticks.
    """
    settings = get_settings()
    batch_size = batch_size or settings.llm_analyzer_batch_size

    log = logger.bind(batch_size=batch_size)
    log.info("analyzer.batch.started")

    candidate_ids = await _candidate_event_ids(db, batch_size)

    processed = 0
    predictions_total = 0
    skipped_locked = 0

    for event_id in candidate_ids:
        # Each event gets its own short transaction. The SELECT...FOR UPDATE
        # SKIP LOCKED is the queue claim — if another worker already holds this
        # row's lock, the SELECT returns None and we move on.
        async with transient_session() as task_db:
            event = await task_db.scalar(
                select(Event)
                .where(Event.id == event_id, Event.status == EventStatus.FETCHED)
                .with_for_update(skip_locked=True)
            )
            if event is None:
                # Another worker claimed it (or it changed status since our scan).
                skipped_locked += 1
                continue

            spend_today = await today_spend_usd(task_db)
            predictions_total += await _process_one(task_db, event, spend_today)
            await task_db.commit()
            processed += 1

    log.info(
        "analyzer.batch.completed",
        events=processed,
        predictions=predictions_total,
        skipped_locked=skipped_locked,
    )
    return {
        "events_processed": processed,
        "predictions_emitted": predictions_total,
        "skipped_locked": skipped_locked,
    }
