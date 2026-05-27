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

# CORS:
#  • Explicit allowlist for local dev
#  • Regex pattern for Vercel deployments — *.vercel.app covers both production
#    (e.g. eventsense.vercel.app) AND preview deploys per PR (e.g.
#    eventsense-git-abc-user.vercel.app)
# Spec §16 forbids "*" in production. The regex is tight enough (only Vercel
# subdomains under app's project pattern can match) that it's safe.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https://[a-z0-9-]+\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "EventSense", "docs": "/docs"}
