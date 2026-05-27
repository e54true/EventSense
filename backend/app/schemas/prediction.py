import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import PredictionDirection, PredictionMagnitude
from app.schemas.outcome import OutcomeRead


class PredictionRead(BaseModel):
    """API response schema for a single prediction."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    ticker: str
    direction: PredictionDirection
    magnitude: PredictionMagnitude
    confidence: float
    reasoning: str
    llm_provider: str
    llm_model: str
    prompt_version: str
    llm_cost_usd: float
    predicted_at: datetime
    created_at: datetime


class PredictionWithOutcomes(PredictionRead):
    """Prediction with its outcomes nested — used in event detail responses."""

    outcomes: list[OutcomeRead] = []
