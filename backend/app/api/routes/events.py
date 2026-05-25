from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event
from app.db.session import get_db
from app.schemas.event import EventListResponse, EventRead, PaginationMeta

router = APIRouter(prefix="/events", tags=["events"])


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
