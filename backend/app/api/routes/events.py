import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Event
from app.db.session import get_db
from app.schemas.event import EventListResponse, EventRead, PaginationMeta
from app.schemas.prediction import PredictionRead

router = APIRouter(prefix="/events", tags=["events"])


class EventDetailResponse(BaseModel):
    """Single event with its predictions eager-loaded."""

    data: EventRead
    predictions: list[PredictionRead]


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
    """Single event with predictions eager-loaded via selectinload (1 + 1 queries, not N+1)."""
    event = await db.scalar(
        select(Event).where(Event.id == event_id).options(selectinload(Event.predictions))
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventDetailResponse(
        data=EventRead.model_validate(event),
        predictions=[PredictionRead.model_validate(p) for p in event.predictions],
    )
