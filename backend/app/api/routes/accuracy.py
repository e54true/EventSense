"""GET /api/v1/accuracy — aggregate LLM alignment rate with optional filters.

Common queries the spec / future dashboard will want:
  - "How accurate is gpt-4o-mini at 24h?"
  - "Which source has the best prediction record?"
  - "Per-ticker accuracy at 7d?"
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Event,
    EventSource,
    OutcomeWindow,
    Prediction,
    PredictionOutcome,
)
from app.db.session import get_db

router = APIRouter(prefix="/accuracy", tags=["accuracy"])


class AccuracyResponse(BaseModel):
    total_outcomes: int
    aligned_count: int
    # alignment_rate is None when total_outcomes is 0 (don't divide by zero,
    # don't lie with "0% accurate when we have no data").
    alignment_rate: float | None
    filters: dict[str, str | None]


@router.get("", response_model=AccuracyResponse)
async def get_accuracy(
    source: EventSource | None = Query(None, description="Filter by event source"),
    ticker: str | None = Query(None, description="Filter by prediction ticker (case-insensitive)"),
    window: OutcomeWindow | None = Query(None, description="Filter by outcome window"),
    model: str | None = Query(None, description="Filter by LLM model name"),
    db: AsyncSession = Depends(get_db),
) -> AccuracyResponse:
    """Compute aligned/total over the filtered set in one round trip.

    SQL: SELECT COUNT(*), SUM(aligned::int) FROM prediction_outcomes
         JOIN predictions ... JOIN events ... WHERE filters
    """
    stmt = (
        select(
            func.count().label("total"),
            # Cast bool → int for SUM. Postgres won't directly coerce bool to
            # float, so int is the safe intermediate; the division to a rate
            # happens in Python below.
            func.sum(cast(PredictionOutcome.aligned, Integer)).label("aligned_sum"),
        )
        .select_from(PredictionOutcome)
        .join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
        .join(Event, Event.id == Prediction.event_id)
    )

    if source is not None:
        stmt = stmt.where(Event.source == source)
    if ticker is not None:
        stmt = stmt.where(Prediction.ticker == ticker.upper())
    if window is not None:
        stmt = stmt.where(PredictionOutcome.window == window)
    if model is not None:
        stmt = stmt.where(Prediction.llm_model == model)

    row = (await db.execute(stmt)).one()
    total = int(row.total or 0)
    aligned = int(row.aligned_sum or 0)
    alignment_rate = (aligned / total) if total > 0 else None

    return AccuracyResponse(
        total_outcomes=total,
        aligned_count=aligned,
        alignment_rate=alignment_rate,
        filters={
            "source": source.value if source else None,
            "ticker": ticker.upper() if ticker else None,
            "window": window.value if window else None,
            "model": model,
        },
    )
