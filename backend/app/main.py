from fastapi import FastAPI

from app.api.routes import api_router
from app.logging_config import configure_logging

configure_logging()


app = FastAPI(
    title="EventSense API",
    version="0.1.0",
    description="Market event analysis platform — backend API",
)

app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "EventSense", "docs": "/docs"}
