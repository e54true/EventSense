import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import any_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import get_settings
from app.db.models import DocumentKind, Event, EventDocument, EventSource, Prediction
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

    id: uuid.UUID
    published_at: datetime
    source: str
    event_type: str
    title: str


class EventContextRead(BaseModel):
    """What the v2 analyzer saw when it processed this event."""

    lookback_days: int
    latest_indicators: list[IndicatorSnapshotRead]
    recent_events: list[RecentEventRead]


class AttachedDocumentRead(BaseModel):
    """A document body downloaded for this event (Phase B+).

    Carries full content_text — the prompt-builder still truncates to keep
    LLM token cost bounded, but the UI shows whatever the storage cap allows.
    """

    doc_kind: DocumentKind
    content_text: str
    raw_url: str
    byte_size: int
    fetched_at: datetime


class EventDetailResponse(BaseModel):
    """Single event with its predictions + outcomes + macro context + attached docs."""

    data: EventRead
    predictions: list[PredictionWithOutcomes]
    context: EventContextRead
    attached_documents: list[AttachedDocumentRead]


@router.get("", response_model=EventListResponse)
async def list_events(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    source: EventSource | None = Query(None, description="Filter by event source"),
    ticker: str | None = Query(
        None, description="Filter by affected ticker (case-insensitive)"
    ),
    event_type: str | None = Query(None, description="Filter by event type"),
    db: AsyncSession = Depends(get_db),
) -> EventListResponse:
    """List events with simple offset pagination + optional filters.

    All filters AND together. `total` reflects the FILTERED count so the
    frontend's infinite scroll knows when to stop.

    Cursor pagination will replace this in a later milestone when volume grows
    (spec §10 — currently this is fine for MVP).
    """
    conditions = []
    if source is not None:
        conditions.append(Event.source == source)
    if ticker is not None:
        # ticker = ANY(affected_tickers) — works on the generic ARRAY type
        # (dialect-specific .contains()/@> isn't available on sa.ARRAY).
        # SQL expression on the LEFT so SQLAlchemy's __eq__ (not str's) builds
        # the clause — ANY(affected_tickers) = :ticker.
        conditions.append(any_(Event.affected_tickers) == ticker.upper())
    if event_type is not None:
        conditions.append(Event.event_type == event_type)

    total = (
        await db.scalar(select(func.count()).select_from(Event).where(*conditions))
    ) or 0

    result = await db.scalars(
        select(Event)
        .where(*conditions)
        .order_by(Event.published_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    events = result.all()

    return EventListResponse(
        data=[EventRead.model_validate(e) for e in events],
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
    )


class EventFiltersResponse(BaseModel):
    """Distinct values present in the events table — drives the filter UI.

    Computed live so a new source/event_type/ticker appears in the filter bar
    without a frontend change.
    """

    sources: list[str]
    event_types: list[str]
    tickers: list[str]


# NOTE: registered before /{event_id} — FastAPI matches in declaration order,
# and "filters" must not be parsed as an event UUID.
@router.get("/filters", response_model=EventFiltersResponse)
async def get_event_filters(db: AsyncSession = Depends(get_db)) -> EventFiltersResponse:
    sources = (await db.scalars(select(Event.source).distinct())).all()
    event_types = (
        await db.scalars(select(Event.event_type).distinct().order_by(Event.event_type))
    ).all()
    tickers = (
        await db.scalars(select(func.unnest(Event.affected_tickers)).distinct())
    ).all()
    return EventFiltersResponse(
        sources=sorted(s.value for s in sources),
        event_types=list(event_types),
        tickers=sorted(tickers),
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
        .options(
            selectinload(Event.predictions).selectinload(Prediction.outcomes),
            selectinload(Event.documents),
        )
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
            id=r.event_id,
            published_at=r.published_at,
            source=r.source,
            event_type=r.event_type,
            title=r.title,
        )
        for r in ctx.recent_events
    ]
    documents = [
        AttachedDocumentRead(
            doc_kind=d.doc_kind,
            content_text=d.content_text,
            raw_url=d.raw_url,
            byte_size=d.byte_size,
            fetched_at=d.fetched_at,
        )
        for d in _sorted_documents(event.documents)
    ]
    return EventDetailResponse(
        data=EventRead.model_validate(event),
        predictions=[PredictionWithOutcomes.model_validate(p) for p in event.predictions],
        context=EventContextRead(
            lookback_days=ctx.lookback_days,
            latest_indicators=indicators,
            recent_events=recent,
        ),
        attached_documents=documents,
    )


_DOC_ORDER: dict[DocumentKind, int] = {
    DocumentKind.PRESS_RELEASE: 0,
    DocumentKind.FILING_COVER: 1,
    DocumentKind.EXHIBIT: 2,
    DocumentKind.TRANSCRIPT: 3,
}


def _sorted_documents(docs: list[EventDocument]) -> list[EventDocument]:
    """PRESS_RELEASE first (most useful for earnings 8-Ks), then cover, exhibits, transcript."""
    return sorted(docs, key=lambda d: _DOC_ORDER.get(d.doc_kind, 99))
