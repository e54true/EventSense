import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import get_settings
from app.db.models import Event, Prediction
from app.db.session import get_db
from app.schemas.event import EventListResponse, EventRead, PaginationMeta
from app.schemas.prediction import PredictionWithOutcomes
from app.services import context_builder

router = APIRouter(prefix="/events", tags=["events"])


class IndicatorSnapshotRead(BaseModel):
    """One indicator's value at/before the event, with 30-day delta if available."""

    indicator_key: str
    value: float
    observed_at: datetime
    delta_30d: float | None


class RecentEventRead(BaseModel):
    """Compact event summary used inside the event-detail context block."""

    published_at: datetime
    source: str
    event_type: str
    title: str


class EventContextRead(BaseModel):
    """What the v2 analyzer saw when it processed this event."""

    lookback_days: int
    latest_indicators: list[IndicatorSnapshotRead]
    recent_events: list[RecentEventRead]


class EventDetailResponse(BaseModel):
    """Single event with its predictions + outcomes + macro context."""

    data: EventRead
    predictions: list[PredictionWithOutcomes]
    context: EventContextRead


@router.get("", response_model=EventListResponse)
async def list_events(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> EventListResponse:
    """List events with simple offset pagination.

    Cursor pagination will replace this in a later milestone when volume grows
    (spec §10 — currently this is fine for MVP).
    """
    total = await db.scalar(select(func.count()).select_from(Event)) or 0

    result = await db.scalars(
        select(Event)
        .order_by(Event.published_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    events = result.all()

    return EventListResponse(
        data=[EventRead.model_validate(e) for e in events],
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
    )


@router.get("/{event_id}", response_model=EventDetailResponse)
async def get_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> EventDetailResponse:
    """Single event with predictions + their outcomes + macro context.

    selectinload chained: events → predictions → outcomes — three queries total,
    not N + M. Without this, accessing `.outcomes` would raise (lazy="raise")
    or trigger an N+1 storm.

    The `context` block reproduces what the v2 analyzer saw at prediction time:
    macro indicators (with 30-day deltas) and the recent-events lookback window.
    """
    event = await db.scalar(
        select(Event)
        .where(Event.id == event_id)
        .options(selectinload(Event.predictions).selectinload(Prediction.outcomes))
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    settings = get_settings()
    ctx = await context_builder.build_context(
        db,
        event,
        lookback_days=settings.analyzer_lookback_days,
        recent_events_cap=settings.analyzer_recent_events_cap,
        watchlist=settings.watchlist,
    )
    indicators = [
        IndicatorSnapshotRead(
            indicator_key=s.indicator_key,
            value=s.value,
            observed_at=s.observed_at,
            delta_30d=s.delta_30d,
        )
        for s in ctx.latest_indicators.values()
    ]
    recent = [
        RecentEventRead(
            published_at=r.published_at,
            source=r.source,
            event_type=r.event_type,
            title=r.title,
        )
        for r in ctx.recent_events
    ]
    return EventDetailResponse(
        data=EventRead.model_validate(event),
        predictions=[PredictionWithOutcomes.model_validate(p) for p in event.predictions],
        context=EventContextRead(
            lookback_days=ctx.lookback_days,
            latest_indicators=indicators,
            recent_events=recent,
        ),
    )
