from fastapi import APIRouter

from app.api.routes import events, prices

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(events.router)
api_router.include_router(prices.router)


@api_router.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
