"""IndicatorObservation: the unified contract that indicator adapters return.

Mirrors `RawEvent` (see app/schemas/raw_event.py) but for the indicators
pipeline. Indicator adapters return list[IndicatorObservation]; the writer
bulk-inserts with ON CONFLICT DO NOTHING against `uq_indicators_key_observed`.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IndicatorObservation(BaseModel):
    """One value of one indicator at one point in time, in source-agnostic form."""

    model_config = ConfigDict(frozen=True)

    indicator_key: str = Field(max_length=40, description="Stable string identifier")
    observed_at: datetime
    value: float
    source: str = Field(max_length=20, description="e.g. FRED, MULTPL, YFINANCE_AGG")
    payload: dict[str, Any] = Field(default_factory=dict)
