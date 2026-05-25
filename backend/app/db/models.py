import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    DateTime,
    Enum,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
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


class PriceSnapshot(Base):
    """One observed price for one ticker at one point in time.

    Schema per EventSense_Spec §6.3. High-volume table — uses bigint PK rather
    than UUID, and skips created_at/updated_at since rows are append-only and
    snapshot_at is already authoritative.

    Index on (ticker, snapshot_at DESC) supports the common access pattern
    "give me the most recent price for AAPL".
    """

    __tablename__ = "price_snapshots"
    __table_args__ = (
        # Dedup: same ticker + timestamp from the same source should never duplicate.
        # Lets us bulk-insert with on-conflict-do-nothing semantics.
        UniqueConstraint("ticker", "snapshot_at", "source", name="uq_price_snapshots_dedup"),
        Index("ix_price_snapshots_ticker_time", "ticker", "snapshot_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Numeric(12, 4) covers prices up to ~99M with 4 decimal places of precision.
    # Decimal (not float) — float would silently lose cents at large values.
    price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="yfinance")
