import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.models import OutcomeWindow


class OutcomeRead(BaseModel):
    """API response for a prediction outcome."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prediction_id: uuid.UUID
    window: OutcomeWindow
    baseline_price: Decimal
    end_price: Decimal
    ticker_return: float
    spy_return: float
    excess_return: float
    aligned: bool
    validated_at: datetime
