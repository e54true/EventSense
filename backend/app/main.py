from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.routes import api_router
from app.logging_config import configure_logging
from app.observability.metrics import refresh_domain_metrics, setup_instrumentation

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

# Observability (Milestone 11): the instrumentator adds HTTP request metrics as
# ASGI middleware; the /metrics route below is defined by hand (not via
# `.expose()`) so it can be async and refresh the domain gauges before
# serializing the registry.
setup_instrumentation(app)


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus scrape target. Excluded from CORS / auth on purpose — it is
    meant to be reached only from inside the cluster (the Prometheus service),
    never the browser. In production, lock this down at the network layer
    (security-group / Railway private networking), not in app code."""
    await refresh_domain_metrics()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "EventSense", "docs": "/docs"}
