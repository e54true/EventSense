import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class PredictionDirection(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class PredictionMagnitude(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PredictionKind(StrEnum):
    """Which side of the prediction this row represents.

    MARKET — broad-index call (SPY / QQQ). Always emitted by the v2 analyzer.
    COMPANY — single-ticker call tied to the triggering event's affected company.
              Only emitted when the event is company-specific (8-K, earnings).
    """

    MARKET = "MARKET"
    COMPANY = "COMPANY"


class OutcomeWindow(StrEnum):
    """Time horizons over which we measure prediction accuracy."""

    H1 = "1h"
    H24 = "24h"
    D7 = "7d"


class DocumentKind(StrEnum):
    """Type of document attached to an event (Phase B+).

    FILING_COVER  — SEC 8-K cover/index document (the form 8-K itself).
    PRESS_RELEASE — SEC EX-99.1 exhibit (typical for item 2.02 earnings releases).
    EXHIBIT       — Other EX-99.x exhibits, supporting materials.
    TRANSCRIPT    — Earnings-call transcript from Whisper (Phase D).
    """

    FILING_COVER = "FILING_COVER"
    PRESS_RELEASE = "PRESS_RELEASE"
    EXHIBIT = "EXHIBIT"
    TRANSCRIPT = "TRANSCRIPT"


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

    # ondelete=CASCADE on the child side; lazy loading suppressed for async safety.
    predictions: Mapped[list["Prediction"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="raise",  # force callers to explicitly opt into loading (selectinload)
    )
    documents: Mapped[list["EventDocument"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class Prediction(Base, TimestampMixin):
    """LLM-generated forecast attached to one Event for one ticker.

    Schema per EventSense_Spec §6.2 + llm_cost_usd added in §9 cost guardrails.
    No unique constraint on (event_id, ticker, prompt_version) — re-running the
    analyzer with a new prompt version intentionally produces a new prediction,
    so old vs new can be compared.
    """

    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_event", "event_id"),
        Index("ix_predictions_ticker_time", "ticker", "predicted_at"),
        Index("ix_predictions_kind_time", "kind", "predicted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    # Default COMPANY keeps v1 analyzer code (which doesn't set kind explicitly)
    # working unchanged. v2 analyzer always sets this explicitly to MARKET or
    # COMPANY per the LLM's response. The DB column itself is NOT NULL.
    kind: Mapped[PredictionKind] = mapped_column(
        Enum(PredictionKind, name="prediction_kind"),
        nullable=False,
        default=PredictionKind.COMPANY,
    )
    direction: Mapped[PredictionDirection] = mapped_column(
        Enum(PredictionDirection, name="prediction_direction"),
        nullable=False,
    )
    magnitude: Mapped[PredictionMagnitude] = mapped_column(
        Enum(PredictionMagnitude, name="prediction_magnitude"),
        nullable=False,
    )
    # LLM-reported certainty about direction (not magnitude) — see spec §9.
    # Stored as float not Decimal; we're not doing financial arithmetic on it.
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(20), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    # USD cost of this single call. Sum-by-day drives the daily cap check.
    llm_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Backref so /events/{id} can eager-load predictions in one query.
    event: Mapped["Event"] = relationship(back_populates="predictions")
    outcomes: Mapped[list["PredictionOutcome"]] = relationship(
        back_populates="prediction",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class PredictionOutcome(Base, TimestampMixin):
    """The realized result of a Prediction at one of (1h, 24h, 7d) post-prediction.

    Schema per EventSense_Spec §6.4. One row per (prediction, window). The
    UNIQUE constraint is the safety net for idempotency — the validator can
    safely re-run without producing duplicate outcomes.

    Returns are stored as plain float (not Decimal) because they're already
    derived from price ratios — precision loss vs. baseline_price/end_price is
    bounded by their Numeric(12,4) source. We're not summing them into money.
    """

    __tablename__ = "prediction_outcomes"
    __table_args__ = (
        UniqueConstraint("prediction_id", "window", name="uq_outcomes_prediction_window"),
        Index("ix_outcomes_prediction", "prediction_id"),
        Index("ix_outcomes_validated_at", "validated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    prediction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("predictions.id", ondelete="CASCADE"),
        nullable=False,
    )
    window: Mapped[OutcomeWindow] = mapped_column(
        Enum(OutcomeWindow, name="outcome_window"),
        nullable=False,
    )
    baseline_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    end_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    ticker_return: Mapped[float] = mapped_column(Float, nullable=False)
    spy_return: Mapped[float] = mapped_column(Float, nullable=False)
    excess_return: Mapped[float] = mapped_column(Float, nullable=False)
    # True if the sign of excess_return matched the prediction direction.
    # NEUTRAL is treated specially — see app.services.alignment.
    aligned: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    prediction: Mapped["Prediction"] = relationship(back_populates="outcomes")


class EventDocument(Base):
    """Large per-event document body (filing text, transcript, exhibit).

    Stored separately from events.payload (JSONB) so events stays small and
    JSONB-indexable while document bodies can be 50-500 KB without bloating
    every events SELECT. Lazy-loaded — callers must selectinload to access.
    """

    __tablename__ = "event_documents"
    __table_args__ = (
        UniqueConstraint("event_id", "doc_kind", name="uq_event_documents_event_kind"),
        Index("ix_event_documents_event", "event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    doc_kind: Mapped[DocumentKind] = mapped_column(
        Enum(DocumentKind, name="document_kind"),
        nullable=False,
    )
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_url: Mapped[str] = mapped_column(String(500), nullable=False)
    byte_size: Mapped[int] = mapped_column(nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event: Mapped["Event"] = relationship(back_populates="documents")


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


class Indicator(Base):
    """One observation of a time-series macro/market indicator.

    Unlike `events`, indicators have no analyzer trigger semantics — they're
    *state* sampled on a cadence (daily for yields, daily for P/E). The v2
    analyzer reads the freshest value per `indicator_key` as context when
    analyzing any triggering event.

    Append-only, mirrors `price_snapshots` table choices (bigint PK, no
    TimestampMixin — `observed_at` is authoritative; `created_at` retained as
    a write-time forensic).
    """

    __tablename__ = "indicators"
    __table_args__ = (
        UniqueConstraint("indicator_key", "observed_at", name="uq_indicators_key_observed"),
        Index(
            "ix_indicators_key_observed_desc",
            "indicator_key",
            "observed_at",
            postgresql_using="btree",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # String (not enum) so adding a new key doesn't require a migration. New
    # indicators are far more common than new event types.
    indicator_key: Mapped[str] = mapped_column(String(40), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Numeric(18, 6) covers yield % (4.275000), P/E (22.350000), and dollar-EPS
    # values ($245.500000) with consistent precision across all indicators.
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
