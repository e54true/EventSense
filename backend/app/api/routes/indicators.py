"""GET /api/v1/indicators/latest — current snapshot of every macro indicator.

Powers the dashboard's "current macro state" panel: one row per indicator_key
showing the freshest value and 30-day delta. Mirrors the data the v2 analyzer
sees as context.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Indicator
from app.db.session import get_db
from app.services.context_builder import _latest_indicator_snapshot

router = APIRouter(prefix="/indicators", tags=["indicators"])


class IndicatorLatestRow(BaseModel):
    indicator_key: str
    value: float
    observed_at: datetime
    delta_30d: float | None


class IndicatorsLatestResponse(BaseModel):
    indicators: list[IndicatorLatestRow]


@router.get("/latest", response_model=IndicatorsLatestResponse)
async def get_latest_indicators(
    db: AsyncSession = Depends(get_db),
) -> IndicatorsLatestResponse:
    """For every distinct indicator_key in the DB, return the freshest snapshot."""
    now = datetime.now(tz=UTC)
    keys = (await db.scalars(select(Indicator.indicator_key).distinct())).all()

    rows: list[IndicatorLatestRow] = []
    for key in sorted(keys):
        snap = await _latest_indicator_snapshot(db, key, now)
        if snap is None:
            continue
        rows.append(
            IndicatorLatestRow(
                indicator_key=snap.indicator_key,
                value=snap.value,
                observed_at=snap.observed_at,
                delta_30d=snap.delta_30d,
            )
        )
    return IndicatorsLatestResponse(indicators=rows)
