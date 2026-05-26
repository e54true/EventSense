from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.logging_config import configure_logging

configure_logging()


app = FastAPI(
    title="EventSense API",
    version="0.1.0",
    description="Market event analysis platform — backend API",
)

# CORS: explicit allowlist for the Next.js dev server (and the eventual Vercel
# preview/prod URLs once we hit M9). Spec §16 explicitly forbids "*" in
# production, so we keep this list tight.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "EventSense", "docs": "/docs"}
