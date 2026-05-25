import structlog
from fastapi import FastAPI

from app.api.routes import api_router
from app.config.settings import get_settings


def configure_logging() -> None:
    """Set up structlog for human-readable dev logs / JSON for prod.

    Picked structlog over stdlib logging for the same reason most modern Python apps do:
    structured key=value logs are far easier to grep and ship to Loki / CloudWatch.
    """
    settings = get_settings()
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.environment == "development":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(processors=processors, cache_logger_on_first_use=True)


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
