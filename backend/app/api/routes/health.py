"""Health endpoints split into liveness + readiness, k8s-style.

- /health        cheap — confirms the process is alive (no I/O)
- /health/ready  checks DB connectivity; load balancer should pull traffic
                  off this instance when it returns 503

Railway / Render / Fly all probe /health by default; Dockerfile HEALTHCHECK
also hits /health (kept fast so frequent probes don't pile up DB queries).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])

# Captured at module import = process start. Drift is negligible at second
# resolution; uptime in seconds is what ops cares about.
_PROCESS_START_AT = datetime.now(UTC)


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float


class ReadyResponse(HealthResponse):
    database: str  # "ok" | "down"


@router.get("", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    """Liveness probe — only proves the ASGI app is still serving.

    Deliberately NO database call. If DB is down, restarting the app doesn't
    fix it; we want load-balancer to keep this pod up so it can return 503
    on /ready instead of being killed and respawned in a loop.
    """
    now = datetime.now(UTC)
    return HealthResponse(
        status="ok",
        uptime_seconds=(now - _PROCESS_START_AT).total_seconds(),
    )


@router.get("/ready", response_model=ReadyResponse)
async def readiness(db: AsyncSession = Depends(get_db)) -> ReadyResponse:
    """Readiness probe — true only when we can also reach the database.

    Returns 503 (via raise HTTPException) when DB is unreachable so that
    load balancers route traffic away rather than serving errors.
    """
    now = datetime.now(UTC)
    uptime = (now - _PROCESS_START_AT).total_seconds()
    try:
        await db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — any DB error means we're not ready
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "uptime_seconds": uptime, "database": "down"},
        ) from None
    return ReadyResponse(status="ok", uptime_seconds=uptime, database="ok")
