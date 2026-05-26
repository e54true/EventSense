import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Prediction
from app.db.session import get_db
from app.schemas.prediction import PredictionRead

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/{prediction_id}", response_model=PredictionRead)
async def get_prediction(
    prediction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PredictionRead:
    """Single prediction by ID. 404 if not found."""
    row = await db.scalar(select(Prediction).where(Prediction.id == prediction_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return PredictionRead.model_validate(row)
