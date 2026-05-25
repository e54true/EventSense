import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ARRAY, DateTime, Enum, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EventSource(StrEnum):
    FRED = "FRED"
    SEC_EDGAR = "SEC_EDGAR"
    FOMC = "FOMC"
    EARNINGS = "EARNINGS"


class EventStatus(StrEnum):
    FETCHED = "FETCHED"
    ANALYZED = "ANALYZED"
    FAILED = "FAILED"
    IGNORED = "IGNORED"


class Event(Base, TimestampMixin):
    """A single discrete occurrence from an official source.

    Schema mirrors EventSense_Spec §6.1. The (source, external_id) unique constraint
    is the dedup mechanism for all adapters — fetchers can blindly insert and rely on
    IntegrityError → no-op.
    """

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_events_source_external_id"),
        Index("ix_events_status_published", "status", "published_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source: Mapped[EventSource] = mapped_column(
        Enum(EventSource, name="event_source"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    affected_tickers: Mapped[list[str]] = mapped_column(
        ARRAY(String(10)),
        nullable=False,
        default=list,
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status"),
        nullable=False,
        default=EventStatus.FETCHED,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
