"""GET /api/v1/pnl — simulated P&L of following every directional call.

"If I had put $STAKE on every BULLISH/BEARISH call (long/short respectively)
from the first event onward, what would I have made?" Computed live from
validated outcomes on every request, so new events show up as soon as the
validator scores them — no batch job, nothing to refresh.

Strategy semantics, modeling caveats, and the SPY benchmark are documented in
app/services/pnl.py. Filters mirror /accuracy so the two dashboards slice
identically.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Event,
    EventSource,
    OutcomeWindow,
    Prediction,
    PredictionKind,
    PredictionOutcome,
)
from app.db.session import get_db
from app.schemas.pnl import PnlResponse
from app.services.pnl import SimTrade, simulate

router = APIRouter(prefix="/pnl", tags=["pnl"])


@router.get("", response_model=PnlResponse)
async def get_pnl(
    source: EventSource | None = Query(None, description="Filter by event source"),
    ticker: str | None = Query(None, description="Filter by prediction ticker (case-insensitive)"),
    window: OutcomeWindow | None = Query(None, description="Filter by outcome window"),
    model: str | None = Query(None, description="Filter by LLM model name"),
    kind: PredictionKind | None = Query(None, description="Filter by MARKET vs COMPANY"),
    stake_usd: float = Query(100.0, gt=0, le=1_000_000, description="Notional per trade"),
    db: AsyncSession = Depends(get_db),
) -> PnlResponse:
    """Same single narrow SELECT shape as /accuracy: outcome volumes are
    modest (hundreds), so pulling the joined rows once and aggregating in
    Python beats a pile of aggregate round trips — and keeps the actual
    simulation a pure, unit-tested function.
    """
    stmt = (
        select(
            PredictionOutcome.window,
            PredictionOutcome.ticker_return,
            PredictionOutcome.spy_return,
            Prediction.direction,
            Prediction.direction_7d,
            Prediction.confidence,
            Prediction.llm_model,
            Prediction.ticker,
            Prediction.predicted_at,
            Event.title,
        )
        .select_from(PredictionOutcome)
        .join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
        .join(Event, Event.id == Prediction.event_id)
        # 1h outcomes are a deprecated legacy window — never traded.
        .where(PredictionOutcome.window != OutcomeWindow.H1)
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

    sim_rows = [
        SimTrade(
            window=r.window,
            direction=r.direction,
            direction_7d=r.direction_7d,
            confidence=r.confidence,
            ticker=r.ticker,
            model=r.llm_model,
            event_title=r.title,
            predicted_at=r.predicted_at,
            ticker_return=r.ticker_return,
            spy_return=r.spy_return,
        )
        for r in rows
    ]

    return simulate(
        sim_rows,
        stake_usd,
        filters={
            "source": source.value if source else None,
            "ticker": ticker.upper() if ticker else None,
            "window": window.value if window else None,
            "model": model,
            "kind": kind.value if kind else None,
        },
    )
