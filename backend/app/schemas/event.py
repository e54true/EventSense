import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.db.models import EventSource, EventStatus


class EventRead(BaseModel):
    """API response schema for a single event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: EventSource
    event_type: str
    external_id: str
    title: str
    payload: dict[str, Any]
    affected_tickers: list[str]
    published_at: datetime
    fetched_at: datetime
    status: EventStatus
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int


class EventListResponse(BaseModel):
    data: list[EventRead]
    meta: PaginationMeta
