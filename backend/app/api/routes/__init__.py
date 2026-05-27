from fastapi import APIRouter

from app.api.routes import accuracy, events, health, predictions, prices

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(events.router)
api_router.include_router(prices.router)
api_router.include_router(predictions.router)
api_router.include_router(accuracy.router)
