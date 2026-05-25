"""RawEvent: the unified contract that all source adapters must return.

This is the *adapter-side* schema (lives between the external API parser and the
DB writer). It deliberately mirrors the Event ORM model but is decoupled from
SQLAlchemy so adapters stay pure (no DB session, no transaction concerns).

Flow:
  external API → adapter parses → list[RawEvent]  ← this file
                                       ↓
                              event_writer.persist()
                                       ↓
                                  events table
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import EventSource


class RawEvent(BaseModel):
    """One event ready to be persisted, in source-agnostic form."""

    model_config = ConfigDict(frozen=True)  # treat as immutable value object

    source: EventSource
    event_type: str = Field(max_length=50)
    external_id: str = Field(max_length=255, description="Unique within (source); used for dedup")
    title: str = Field(max_length=500)
    payload: dict[str, Any]
    affected_tickers: list[str] = Field(default_factory=list)
    published_at: datetime
