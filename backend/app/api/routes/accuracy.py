"""GET /api/v1/accuracy — aggregate LLM alignment rate with optional filters.

Common queries the spec / future dashboard will want:
  - "How accurate is the default model at 24h?"
  - "Which source has the best prediction record?"
  - "Per-ticker accuracy at 7d?"

Besides the headline rate, the response carries:
  - baselines: what trivial constant strategies (always-BULLISH / BEARISH /
    NEUTRAL) would have scored on the SAME outcome set. An alignment rate
    only means something relative to these — markets drift upward, so
    always-BULLISH is well above 50% at 7d.
  - calibration: alignment rate bucketed by the model's stated confidence.
    A calibrated forecaster's 0.7-bucket should align ~70% of the time.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Event,
    EventSource,
    OutcomeWindow,
    Prediction,
    PredictionDirection,
    PredictionKind,
    PredictionOutcome,
)
from app.db.session import get_db
from app.services import alignment

router = APIRouter(prefix="/accuracy", tags=["accuracy"])

# Confidence buckets for the calibration table: [lo, hi) except the last.
_CALIBRATION_BUCKETS: list[tuple[float, float]] = [
    (0.0, 0.55),
    (0.55, 0.65),
    (0.65, 0.75),
    (0.75, 0.85),
    (0.85, 1.01),
]


class CalibrationBucket(BaseModel):
    bucket: str  # e.g. "0.55-0.65"
    total: int
    aligned: int
    alignment_rate: float | None


class AccuracyResponse(BaseModel):
    total_outcomes: int
    aligned_count: int
    # alignment_rate is None when total_outcomes is 0 (don't divide by zero,
    # don't lie with "0% accurate when we have no data").
    alignment_rate: float | None
    # Constant-strategy comparison over the same filtered outcome set.
    baselines: dict[str, float | None]
    calibration: list[CalibrationBucket]
    filters: dict[str, str | None]


@router.get("", response_model=AccuracyResponse)
async def get_accuracy(
    source: EventSource | None = Query(None, description="Filter by event source"),
    ticker: str | None = Query(None, description="Filter by prediction ticker (case-insensitive)"),
    window: OutcomeWindow | None = Query(None, description="Filter by outcome window"),
    model: str | None = Query(None, description="Filter by LLM model name"),
    kind: PredictionKind | None = Query(None, description="Filter by MARKET vs COMPANY"),
    db: AsyncSession = Depends(get_db),
) -> AccuracyResponse:
    """Fetch the filtered outcome rows once, derive rate + baselines +
    calibration in Python. Outcome volumes are modest (thousands, not
    millions) so a single narrow SELECT beats three aggregate round trips.
    """
    stmt = (
        select(
            PredictionOutcome.window,
            PredictionOutcome.ticker_return,
            PredictionOutcome.aligned,
            Prediction.confidence,
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
    if kind is not None:
        stmt = stmt.where(Prediction.kind == kind)

    rows = (await db.execute(stmt)).all()

    total = len(rows)
    aligned = sum(1 for r in rows if r.aligned)
    alignment_rate = (aligned / total) if total > 0 else None

    # Constant-strategy baselines on the same rows, using the same per-window
    # neutral bands the validator applies.
    baselines: dict[str, float | None] = {}
    for name, direction in (
        ("always_bullish", PredictionDirection.BULLISH),
        ("always_bearish", PredictionDirection.BEARISH),
        ("always_neutral", PredictionDirection.NEUTRAL),
    ):
        if total == 0:
            baselines[name] = None
            continue
        hits = sum(1 for r in rows if alignment.is_aligned(direction, r.ticker_return, r.window))
        baselines[name] = hits / total

    calibration: list[CalibrationBucket] = []
    for lo, hi in _CALIBRATION_BUCKETS:
        in_bucket = [r for r in rows if lo <= r.confidence < hi]
        n = len(in_bucket)
        n_aligned = sum(1 for r in in_bucket if r.aligned)
        calibration.append(
            CalibrationBucket(
                bucket=f"{lo:.2f}-{min(hi, 1.0):.2f}",
                total=n,
                aligned=n_aligned,
                alignment_rate=(n_aligned / n) if n > 0 else None,
            )
        )

    return AccuracyResponse(
        total_outcomes=total,
        aligned_count=aligned,
        alignment_rate=alignment_rate,
        baselines=baselines,
        calibration=calibration,
        filters={
            "source": source.value if source else None,
            "ticker": ticker.upper() if ticker else None,
            "window": window.value if window else None,
            "model": model,
            "kind": kind.value if kind else None,
        },
    )
