"""Shared logging config used by both the FastAPI app and Celery workers.

Why this lives outside `app/main.py`: Celery workers don't import main.py — they
import `app.workers.celery_app`. Putting `configure_logging()` in a shared module
means every entrypoint (uvicorn, celery worker, celery beat, alembic) can call it.

structlog wraps stdlib logging so libraries that use stdlib `logging` (sqlalchemy,
celery, alembic) still flow through the same handler. We attach a `ProcessorFormatter`
to the stdlib root logger so its records get rendered with our processor chain.
"""

import logging

import structlog

from app.config.settings import get_settings


def configure_logging() -> None:
    settings = get_settings()

    timestamper = structlog.processors.TimeStamper(fmt="iso")

    # Shared processors run on every event regardless of source (structlog or stdlib).
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.environment == "development":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            # Hand off to ProcessorFormatter on the stdlib side — the renderer runs there
            # so stdlib log records and structlog records share the exact same output.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Stdlib side: a single handler with our processor chain.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            # Strip the meta-key that wrap_for_formatter adds before rendering.
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # Tone down chatty libs.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
