"""Build the lookback context that the v2 analyzer prompt needs.

For a given triggering event, gather:
  1. Recent events from the past N days (excluding the triggering event itself)
  2. Latest value of every indicator at-or-before the triggering event's
     published_at, plus a 30-day-prior value for change computation

The output is a frozen dataclass that the prompt builder renders as compact
tables (token-efficient — full payloads would balloon the prompt).
"""

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    DocumentKind,
    Event,
    EventDocument,
    Indicator,
    OutcomeWindow,
    Prediction,
    PredictionDirection,
    PredictionKind,
    PredictionMagnitude,
    PredictionOutcome,
    PriceSnapshot,
)

logger = structlog.get_logger(__name__)

# Window over which we compute "indicator change" (delta_30d). Aligns with the
# default analyzer_lookback_days so the LLM sees one full window's drift.
_DELTA_WINDOW = timedelta(days=30)

# Cap per-document inlined chars in the prompt. Storage cap (in document_fetcher)
# is 80K — this 20K keeps prompt token cost bounded even when both PRESS_RELEASE
# and FILING_COVER are attached.
_PROMPT_INLINE_PER_DOC_CHARS = 20_000


@dataclass(frozen=True, slots=True)
class IndicatorSnapshot:
    """One indicator's freshest value + a window-ago value for delta computation."""

    indicator_key: str
    value: float
    observed_at: datetime
    # Value 30 days before observed_at, when available. Useful for "yields up
    # 25bp this month" style reasoning.
    value_30d_ago: float | None
    delta_30d: float | None


@dataclass(frozen=True, slots=True)
class PriorOutcome:
    """One validated outcome of a prior prediction. Only outcomes whose
    validated_at <= triggering_event.published_at are included (leak prevention)."""

    window: OutcomeWindow
    ticker_return: float
    spy_return: float
    excess_return: float
    aligned: bool


@dataclass(frozen=True, slots=True)
class PriorPrediction:
    """One past prediction the analyzer made on a prior event."""

    ticker: str
    kind: PredictionKind
    direction: PredictionDirection
    magnitude: PredictionMagnitude
    confidence: float
    reasoning: str
    prompt_version: str
    outcomes: list[PriorOutcome]


@dataclass(frozen=True, slots=True)
class RecentEventSummary:
    """Compact representation of a past event for the v2 prompt table.

    Carries through the full payload (so renderer can pull a per-source
    highlight line) plus any prior predictions + already-validated outcomes
    (so the LLM can see its own track record without prescribed self-calibration).
    """

    published_at: datetime
    source: str
    event_type: str
    title: str
    payload: dict[str, Any]
    prior_predictions: list[PriorPrediction]


@dataclass(frozen=True, slots=True)
class AttachedDocument:
    """One document attached to the triggering event (Phase B)."""

    doc_kind: DocumentKind
    content_text: str
    raw_url: str


@dataclass(frozen=True, slots=True)
class MarketStateRow:
    """Trailing price action for one ticker, as of the triggering event.

    Computed from daily-resampled price_snapshots at-or-before published_at
    (leak-safe). None fields = not enough history in the snapshot table.
    """

    ticker: str
    return_1d: float | None
    return_5d: float | None
    return_20d: float | None
    vol_20d_annualized: float | None


@dataclass(frozen=True, slots=True)
class TrackRecordRow:
    """Aggregate alignment stats for one (window, kind, direction) slice of
    the analyzer's own recent history — only outcomes validated before the
    triggering event (leak prevention)."""

    window: OutcomeWindow
    kind: PredictionKind
    direction: PredictionDirection
    total: int
    aligned: int


@dataclass(frozen=True, slots=True)
class AnalyzerContext:
    """Everything the v2/v3 prompt template needs for one triggering event."""

    triggering_event: Event
    recent_events: list[RecentEventSummary]
    latest_indicators: dict[str, IndicatorSnapshot]
    attached_documents: list[AttachedDocument]
    watchlist: list[str]
    lookback_days: int
    # v3 additions — default empty so v2 call sites / fixtures stay valid.
    market_state: list[MarketStateRow] = field(default_factory=list)
    track_record: list[TrackRecordRow] = field(default_factory=list)


async def _recent_events(
    db: AsyncSession,
    triggering_event: Event,
    lookback_days: int,
    cap: int,
) -> list[RecentEventSummary]:
    """Past N days of events, newest-first, capped, excluding the triggering one.

    The window is [triggering_event.published_at - N days, triggering_event.published_at]
    — anchored on the EVENT, not on now(). This avoids data leakage when
    re-analyzing historical backfill: the prompt must only see things known
    AT THE TIME of the triggering event, never anything after.

    Each event's predictions are eager-loaded along with their outcomes.
    Outcomes are filtered in Python (not SQL) by validated_at — only those
    validated AT-OR-BEFORE the triggering event are kept; later validations
    would leak future information into the prompt.
    """
    cutoff = triggering_event.published_at - timedelta(days=lookback_days)
    rows = (
        await db.scalars(
            select(Event)
            .where(
                Event.published_at >= cutoff,
                Event.published_at <= triggering_event.published_at,
                Event.id != triggering_event.id,
            )
            .options(selectinload(Event.predictions).selectinload(Prediction.outcomes))
            .order_by(Event.published_at.desc())
            .limit(cap)
        )
    ).all()

    summaries: list[RecentEventSummary] = []
    for event in rows:
        prior_predictions: list[PriorPrediction] = []
        for p in event.predictions:
            outcomes = [
                PriorOutcome(
                    window=o.window,
                    ticker_return=o.ticker_return,
                    spy_return=o.spy_return,
                    excess_return=o.excess_return,
                    aligned=o.aligned,
                )
                for o in p.outcomes
                if o.validated_at <= triggering_event.published_at
            ]
            prior_predictions.append(
                PriorPrediction(
                    ticker=p.ticker,
                    kind=p.kind,
                    direction=p.direction,
                    magnitude=p.magnitude,
                    confidence=p.confidence,
                    reasoning=p.reasoning,
                    prompt_version=p.prompt_version,
                    outcomes=outcomes,
                )
            )

        summaries.append(
            RecentEventSummary(
                published_at=event.published_at,
                source=str(event.source.value),
                event_type=event.event_type,
                title=event.title,
                payload=event.payload or {},
                prior_predictions=prior_predictions,
            )
        )
    return summaries


async def _latest_indicator_snapshot(
    db: AsyncSession, indicator_key: str, at: datetime
) -> IndicatorSnapshot | None:
    """Most recent observation for `indicator_key` at-or-before `at`, plus the
    value from ~30 days prior for delta computation."""
    latest_stmt = (
        select(Indicator.observed_at, Indicator.value)
        .where(
            Indicator.indicator_key == indicator_key,
            Indicator.observed_at <= at,
        )
        .order_by(Indicator.observed_at.desc())
        .limit(1)
    )
    latest = (await db.execute(latest_stmt)).first()
    if latest is None:
        return None

    # Look up the closest observation to (latest_at - 30d) by descending order
    # — we'd accept anything within ±2 days of the target so weekends/holidays
    # don't drop the delta.
    prior_target = latest.observed_at - _DELTA_WINDOW
    prior_stmt = (
        select(Indicator.observed_at, Indicator.value)
        .where(
            and_(
                Indicator.indicator_key == indicator_key,
                # Both bounds matter: without the lower one, a data gap would
                # silently substitute a months-old observation as the "30d ago"
                # value and corrupt delta_30d.
                Indicator.observed_at >= prior_target - timedelta(days=2),
                Indicator.observed_at <= prior_target + timedelta(days=2),
            )
        )
        .order_by(Indicator.observed_at.desc())
        .limit(1)
    )
    prior = (await db.execute(prior_stmt)).first()

    latest_value = float(latest.value)
    if prior is None:
        return IndicatorSnapshot(
            indicator_key=indicator_key,
            value=latest_value,
            observed_at=latest.observed_at,
            value_30d_ago=None,
            delta_30d=None,
        )
    prior_value = float(prior.value)
    return IndicatorSnapshot(
        indicator_key=indicator_key,
        value=latest_value,
        observed_at=latest.observed_at,
        value_30d_ago=prior_value,
        delta_30d=latest_value - prior_value,
    )


async def _all_latest_indicators(
    db: AsyncSession, at: datetime
) -> dict[str, IndicatorSnapshot]:
    """For every indicator_key present in the DB, the freshest snapshot at-or-before `at`."""
    keys_result = await db.scalars(select(Indicator.indicator_key).distinct())
    snapshots: dict[str, IndicatorSnapshot] = {}
    for key in keys_result.all():
        snap = await _latest_indicator_snapshot(db, key, at)
        if snap is not None:
            snapshots[key] = snap
    return snapshots


# Trailing-return horizons (in trading days) for the market-state table.
_MARKET_STATE_HORIZONS = (1, 5, 20)
# Daily snapshots needed: 20d return + a buffer for partial days.
_MARKET_STATE_FETCH_LIMIT = 35
# How far back the self-track-record aggregation looks from the trigger.
_TRACK_RECORD_LOOKBACK = timedelta(days=60)


async def _market_state_row(
    db: AsyncSession, ticker: str, at: datetime
) -> MarketStateRow:
    """Trailing returns + realized vol for one ticker as of `at` (leak-safe)."""
    rows = (
        await db.execute(
            select(PriceSnapshot.snapshot_at, PriceSnapshot.price)
            .where(
                PriceSnapshot.ticker == ticker,
                PriceSnapshot.snapshot_at <= at,
            )
            .order_by(PriceSnapshot.snapshot_at.desc())
            .limit(_MARKET_STATE_FETCH_LIMIT)
        )
    ).all()

    # Resample to one close per calendar day (keep the latest within each day),
    # then order oldest → newest.
    by_day: dict[str, float] = {}
    for r in rows:  # rows are newest-first; first hit per day wins
        day = r.snapshot_at.date().isoformat()
        if day not in by_day:
            by_day[day] = float(r.price)
    closes = [by_day[d] for d in sorted(by_day)]

    def horizon_return(days: int) -> float | None:
        if len(closes) < days + 1 or closes[-1 - days] <= 0:
            return None
        return closes[-1] / closes[-1 - days] - 1

    vol: float | None = None
    if len(closes) >= 21:
        daily_rets = [
            closes[i] / closes[i - 1] - 1
            for i in range(len(closes) - 20, len(closes))
            if closes[i - 1] > 0
        ]
        if len(daily_rets) >= 2:
            vol = statistics.pstdev(daily_rets) * (252**0.5)

    r1, r5, r20 = (horizon_return(d) for d in _MARKET_STATE_HORIZONS)
    return MarketStateRow(
        ticker=ticker,
        return_1d=r1,
        return_5d=r5,
        return_20d=r20,
        vol_20d_annualized=vol,
    )


async def _market_state(
    db: AsyncSession, triggering_event: Event, watchlist: list[str]
) -> list[MarketStateRow]:
    """Market-state rows for the index baselines + the event's own company."""
    tickers = ["SPY", "QQQ"]
    for t in triggering_event.affected_tickers or []:
        if t in watchlist and t not in tickers:
            tickers.append(t)
    return [
        await _market_state_row(db, t, triggering_event.published_at) for t in tickers
    ]


async def _track_record(
    db: AsyncSession, triggering_event: Event
) -> list[TrackRecordRow]:
    """Aggregate the analyzer's own recent hit rate, sliced by
    (window, kind, direction-as-scored).

    Leak-safe: only outcomes validated at-or-before the triggering event, for
    predictions made within the lookback window before it.
    """
    at = triggering_event.published_at
    rows = (
        await db.execute(
            select(
                PredictionOutcome.window,
                Prediction.kind,
                Prediction.direction,
                Prediction.direction_7d,
                PredictionOutcome.aligned,
            )
            .join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
            .where(
                PredictionOutcome.validated_at <= at,
                Prediction.predicted_at >= at - _TRACK_RECORD_LOOKBACK,
            )
        )
    ).all()

    counts: dict[tuple[OutcomeWindow, PredictionKind, PredictionDirection], list[int]] = {}
    for r in rows:
        # Score against the direction the validator actually used per window.
        if r.window == OutcomeWindow.D7 and r.direction_7d is not None:
            direction = r.direction_7d
        else:
            direction = r.direction
        key = (r.window, r.kind, direction)
        bucket = counts.setdefault(key, [0, 0])
        bucket[0] += 1
        bucket[1] += int(r.aligned)

    return [
        TrackRecordRow(window=w, kind=k, direction=d, total=t, aligned=a)
        for (w, k, d), (t, a) in sorted(
            counts.items(), key=lambda kv: (kv[0][0].value, kv[0][1].value, kv[0][2].value)
        )
    ]


async def _attached_documents(
    db: AsyncSession, triggering_event: Event
) -> list[AttachedDocument]:
    """Pull all event_documents rows for the triggering event, content truncated
    to the per-document prompt cap."""
    rows = (
        await db.execute(
            select(
                EventDocument.doc_kind,
                EventDocument.content_text,
                EventDocument.raw_url,
            ).where(EventDocument.event_id == triggering_event.id)
        )
    ).all()
    return [
        AttachedDocument(
            doc_kind=r.doc_kind,
            content_text=r.content_text[:_PROMPT_INLINE_PER_DOC_CHARS],
            raw_url=r.raw_url,
        )
        for r in rows
    ]


async def build_context(
    db: AsyncSession,
    triggering_event: Event,
    *,
    lookback_days: int,
    recent_events_cap: int,
    watchlist: list[str],
) -> AnalyzerContext:
    """Assemble the AnalyzerContext for one triggering event.

    Pure DB reads — the analyzer holds the FOR UPDATE lock on the triggering
    event in its own transaction; this function is invoked inside that.
    """
    log = logger.bind(event_id=str(triggering_event.id), lookback_days=lookback_days)
    log.info("context_builder.started")

    recent = await _recent_events(
        db, triggering_event, lookback_days=lookback_days, cap=recent_events_cap
    )
    indicators = await _all_latest_indicators(db, triggering_event.published_at)
    documents = await _attached_documents(db, triggering_event)
    market_state = await _market_state(db, triggering_event, watchlist)
    track_record = await _track_record(db, triggering_event)

    log.info(
        "context_builder.completed",
        recent_events=len(recent),
        indicator_keys=len(indicators),
        attached_documents=len(documents),
        market_state_rows=len(market_state),
        track_record_rows=len(track_record),
    )
    return AnalyzerContext(
        triggering_event=triggering_event,
        recent_events=recent,
        latest_indicators=indicators,
        attached_documents=documents,
        watchlist=watchlist,
        lookback_days=lookback_days,
        market_state=market_state,
        track_record=track_record,
    )
