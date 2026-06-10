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

import statistics
import uuid
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.models import (
    Event,
    EventDocument,
    EventSource,
    EventStatus,
    Prediction,
    PredictionDirection,
    PredictionKind,
)
from app.db.session import transient_session
from app.llm import clients
from app.llm.cost import estimate_cost_usd, today_spend_usd
from app.llm.router import ModelChoice, choose_model
from app.llm.schemas import EventAnalysis, TickerImpact
from app.services import context_builder

# Tickers eligible for kind=MARKET impacts. The two index proxies — SPY tracks
# S&P 500, QQQ tracks Nasdaq-100. The analyzer rejects MARKET impacts with any
# other ticker (treating them as LLM hallucination).
_MARKET_TICKERS: frozenset[str] = frozenset({"SPY", "QQQ"})

# Event types we treat as "company-specific" — only these are allowed to have
# kind=COMPANY impacts. Everything else (macro releases) emits MARKET-only.
_COMPANY_EVENT_TYPES: frozenset[str] = frozenset({"8K_FILING", "EARNINGS_REPORT"})

# Phase B: how long to wait for SEC document body fetch before analyzing
# anyway. 8-K events that arrive without yet-fetched documents get held back
# from the analyze queue for this long; after that we fall through with
# whatever's attached (possibly nothing — graceful degrade).
_DOC_WAIT_SECONDS = 300

logger = structlog.get_logger(__name__)


async def _process_one(db: AsyncSession, event: Event, spend_today: float) -> int:
    """Run LLM on `event`, write predictions, transition status. Returns predictions emitted.

    The caller owns the transaction; this function does NOT commit. The caller
    commits after this returns (success or failure path).
    """
    settings = get_settings()
    log = logger.bind(event_id=str(event.id), source=event.source.value)
    choice = choose_model(event.source, event.event_type, spend_today)
    watchlist = settings.watchlist

    if settings.analyzer_prompt_version in ("v2", "v3"):
        ctx = await context_builder.build_context(
            db,
            event,
            lookback_days=settings.analyzer_lookback_days,
            recent_events_cap=settings.analyzer_recent_events_cap,
            watchlist=watchlist,
        )
        if settings.analyzer_prompt_version == "v3":
            prompt = clients.build_prompt_v3(ctx)
        else:
            prompt = clients.build_prompt_v2(ctx)
    else:
        prompt = clients.build_prompt_v1(event.payload, watchlist)

    # Self-consistency: premium-routed (high-stakes) events get N independent
    # calls; per-ticker direction is decided by majority vote. Directional
    # majority voting reliably beats a single sample on forecast-style tasks,
    # and high-stakes events are rare enough that N-fold cost stays trivial.
    n_calls = (
        settings.analyzer_consensus_calls
        if choice.model == settings.llm_premium_model
        else 1
    )
    results: list[clients.LLMCallResult] = []
    last_error: Exception | None = None
    for _ in range(max(1, n_calls)):
        try:
            results.append(await clients.analyze_event(choice, prompt))
        except Exception as exc:  # any provider error fails this call only
            last_error = exc
            log.warning(
                "analyzer.llm_call_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )

    if not results:
        event.status = EventStatus.FAILED
        event.failure_reason = (
            f"LLM call failed: {type(last_error).__name__}: {last_error}"[:1000]
        )
        return 0

    analysis = _consensus_analysis([r.analysis for r in results])
    cost = sum(
        estimate_cost_usd(choice.model, r.prompt_tokens, r.completion_tokens)
        for r in results
    )
    predictions = _build_predictions(event, analysis, choice, cost)
    db.add_all(predictions)
    event.status = EventStatus.ANALYZED
    event.failure_reason = None
    # Persist the thesis paragraph so the frontend can show it for human review.
    event.llm_summary = analysis.summary

    log.info(
        "analyzer.event_done",
        predictions=len(predictions),
        model=choice.model,
        consensus_calls=len(results),
        cost_usd=round(cost, 6),
        prompt_tokens=sum(r.prompt_tokens for r in results),
        completion_tokens=sum(r.completion_tokens for r in results),
        prompt_version=settings.analyzer_prompt_version,
    )
    return len(predictions)


def _mode[T](values: Sequence[T], tie_fallback: T) -> T:
    """Most common value; explicit fallback on an exact tie (or empty input)."""
    if not values:
        return tie_fallback
    ranked = Counter(values).most_common()
    if len(ranked) > 1 and ranked[1][1] == ranked[0][1]:
        return tie_fallback
    return ranked[0][0]


def _consensus_analysis(analyses: list[EventAnalysis]) -> EventAnalysis:
    """Merge N independent EventAnalysis samples into one by majority vote.

    Per (ticker, kind) group: modal direction (tie → NEUTRAL — disagreement IS
    low conviction), modal magnitude (tie → MEDIUM), median confidence, and
    the reasoning text from the first sample that voted with the majority.
    Summary comes from the first sample. N=1 passes straight through.
    """
    if len(analyses) == 1:
        return analyses[0]

    grouped: dict[tuple[str, str], list[TickerImpact]] = {}
    order: list[tuple[str, str]] = []
    for a in analyses:
        for impact in a.impacts:
            key: tuple[str, str] = (impact.ticker, impact.kind)
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(impact)

    merged: list[TickerImpact] = []
    majority = len(analyses) / 2
    for key in order:
        votes = grouped[key]
        # Drop tickers that only a minority of samples emitted at all.
        if len(votes) <= majority:
            continue
        direction = _mode([v.direction for v in votes], "NEUTRAL")
        d7_votes = [v.direction_7d for v in votes if v.direction_7d is not None]
        direction_7d = _mode(d7_votes, "NEUTRAL") if d7_votes else None
        magnitude = _mode([v.magnitude for v in votes], "MEDIUM")
        confidence = float(statistics.median([v.confidence for v in votes]))
        reasoning = next(
            (v.reasoning for v in votes if v.direction == direction),
            votes[0].reasoning,
        )
        merged.append(
            TickerImpact(
                ticker=key[0],
                kind=votes[0].kind,
                direction=direction,
                direction_7d=direction_7d,
                magnitude=magnitude,
                confidence=confidence,
                reasoning=reasoning,
            )
        )

    return EventAnalysis(summary=analyses[0].summary, impacts=merged)


def _build_predictions(
    event: Event,
    analysis: EventAnalysis,
    choice: ModelChoice,
    cost_usd: float,
) -> list[Prediction]:
    """Turn one EventAnalysis into N Prediction ORM rows.

    Cost is attributed only to the first prediction — sum-by-day still gives the
    right total, and per-prediction division would create misleading fractions.

    Validation rules (kind-aware, post-v2):
      - kind=MARKET ⇒ ticker MUST be SPY or QQQ; other tickers are dropped as
        LLM hallucination.
      - kind=COMPANY ⇒ ticker MUST be in event.affected_tickers AND in the
        watchlist; macro-event COMPANY impacts are also dropped (LLM should
        only emit COMPANY for 8-K / earnings).
    """
    watchlist = set(get_settings().watchlist)
    affected = set(event.affected_tickers or [])
    is_company_event = event.event_type in _COMPANY_EVENT_TYPES

    # `predicted_at` anchors the validator's outcome calculation
    # (baseline = price at predicted_at; end = price at predicted_at + window).
    # For fresh events, event.published_at ≈ now within seconds, so this is
    # equivalent to the old `now()` behavior. For backfilled historical events
    # (earnings_history surfacing 4-month-old reports), it correctly anchors
    # on the actual market reaction time rather than the analyzer-run time.
    predicted_at = event.published_at
    rows: list[Prediction] = []
    for i, impact in enumerate(analysis.impacts):
        kind = PredictionKind(impact.kind)
        log = logger.bind(event_id=str(event.id), ticker=impact.ticker, kind=kind.value)

        if kind == PredictionKind.MARKET:
            if impact.ticker not in _MARKET_TICKERS:
                log.warning("analyzer.market_impact_bad_ticker")
                continue
        else:  # COMPANY
            if not is_company_event:
                log.warning("analyzer.company_impact_on_macro_event")
                continue
            if impact.ticker not in watchlist:
                log.warning("analyzer.hallucinated_ticker")
                continue
            if affected and impact.ticker not in affected:
                # The LLM picked a watchlist ticker that isn't the event's own
                # company — possible for spillover ("AAPL guidance hits TSM"),
                # but the v2 prompt explicitly forbids it. Drop.
                log.warning("analyzer.company_impact_off_target")
                continue

        rows.append(
            Prediction(
                event_id=event.id,
                ticker=impact.ticker,
                kind=kind,
                direction=impact.direction,
                direction_7d=(
                    PredictionDirection(impact.direction_7d)
                    if impact.direction_7d is not None
                    else None
                ),
                magnitude=impact.magnitude,
                confidence=impact.confidence,
                reasoning=impact.reasoning,
                llm_provider=choice.provider,
                llm_model=choice.model,
                prompt_version=get_settings().analyzer_prompt_version,
                llm_cost_usd=cost_usd if i == 0 else 0.0,
                predicted_at=predicted_at,
            )
        )
    return rows


async def _candidate_event_ids(db: AsyncSession, limit: int) -> list[uuid.UUID]:
    """Cheap read-only query: which events look pending? Lock comes later, per event.

    Phase B: 8-K events that landed in the last 5 minutes and don't yet have
    an event_documents row are *deferred* — the document fetcher needs time
    to run. After 5 min we fall through and analyze with whatever's there.
    """
    wait_cutoff = datetime.now(UTC) - timedelta(seconds=_DOC_WAIT_SECONDS)
    has_doc = exists().where(EventDocument.event_id == Event.id)
    # Eligible iff NOT (8-K AND fetched recently AND no docs yet).
    not_waiting = or_(
        Event.source != EventSource.SEC_EDGAR,
        Event.event_type != "8K_FILING",
        Event.fetched_at < wait_cutoff,
        has_doc,
    )
    result = await db.scalars(
        select(Event.id)
        .where(Event.status == EventStatus.FETCHED, not_waiting)
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
