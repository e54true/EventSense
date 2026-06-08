"""Build the lookback context that the v2 analyzer prompt needs.

For a given triggering event, gather:
  1. Recent events from the past N days (excluding the triggering event itself)
  2. Latest value of every indicator at-or-before the triggering event's
     published_at, plus a 30-day-prior value for change computation

The output is a frozen dataclass that the prompt builder renders as compact
tables (token-efficient — full payloads would balloon the prompt).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, Indicator

logger = structlog.get_logger(__name__)

# Window over which we compute "indicator change" (delta_30d). Aligns with the
# default analyzer_lookback_days so the LLM sees one full window's drift.
_DELTA_WINDOW = timedelta(days=30)


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
class RecentEventSummary:
    """Compact representation of a past event for the v2 prompt table."""

    published_at: datetime
    source: str
    event_type: str
    title: str


@dataclass(frozen=True, slots=True)
class AnalyzerContext:
    """Everything the v2 prompt template needs for one triggering event."""

    triggering_event: Event
    recent_events: list[RecentEventSummary]
    latest_indicators: dict[str, IndicatorSnapshot]
    watchlist: list[str]
    lookback_days: int


async def _recent_events(
    db: AsyncSession,
    triggering_event: Event,
    lookback_days: int,
    cap: int,
) -> list[RecentEventSummary]:
    """Past N days of events, newest-first, capped, excluding the triggering one."""
    cutoff = triggering_event.published_at - timedelta(days=lookback_days)
    stmt = (
        select(
            Event.published_at,
            Event.source,
            Event.event_type,
            Event.title,
        )
        .where(
            Event.published_at >= cutoff,
            Event.published_at <= triggering_event.published_at,
            Event.id != triggering_event.id,
        )
        .order_by(Event.published_at.desc())
        .limit(cap)
    )
    rows = (await db.execute(stmt)).all()
    return [
        RecentEventSummary(
            published_at=r.published_at,
            source=str(r.source.value if hasattr(r.source, "value") else r.source),
            event_type=r.event_type,
            title=r.title,
        )
        for r in rows
    ]


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

    log.info(
        "context_builder.completed",
        recent_events=len(recent),
        indicator_keys=len(indicators),
    )
    return AnalyzerContext(
        triggering_event=triggering_event,
        recent_events=recent,
        latest_indicators=indicators,
        watchlist=watchlist,
        lookback_days=lookback_days,
    )
