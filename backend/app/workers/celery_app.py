"""Celery application — broker, queue routing, beat schedule.

The Celery app is intentionally separate from the FastAPI app:
  - `app.main:app`  → ASGI server, request/response
  - `app.workers.celery_app:celery_app`  → background workers + scheduler

Both share the same code (models, adapters, settings) but run as distinct processes.

Queues (spec §8):
  - fetch_queue     IO-bound external API calls (FRED, SEC, FOMC, yfinance)
  - analyze_queue   LLM calls (rate-limited, lower concurrency)
  - validate_queue  price-fetch + outcome calculation

Only fetch_queue is exercised in Milestone 2; the other routes are declared up-front
so we don't need to migrate task names later.
"""

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

from app.config.settings import get_settings
from app.logging_config import configure_logging


# Celery normally configures its own logging — we hijack it via the setup_logging
# signal so worker / beat logs use the same structlog formatting as FastAPI.
@setup_logging.connect
def _configure_celery_logging(**_kwargs: object) -> None:
    configure_logging()

settings = get_settings()

celery_app = Celery(
    "eventsense",
    broker=settings.redis_url,
    backend=settings.redis_url,
    # Auto-discover tasks in these modules so we don't have to import them by hand.
    include=["app.tasks.fetchers"],
)

celery_app.conf.update(
    # Serialization — JSON is enough for our task args (primitives, UUIDs as str).
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Don't ack tasks until they finish — if a worker crashes mid-task, the broker
    # redelivers to another worker. Trade-off: a task could run twice on crash, but
    # our tasks are idempotent (DB unique constraints), so this is the safer default.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Result expiry: we don't actually consume task results, just need them for retries.
    result_expires=3600,
)

# Route tasks to dedicated queues so a slow LLM call doesn't block a quick FRED fetch.
celery_app.conf.task_routes = {
    "app.tasks.fetchers.*": {"queue": "fetch_queue"},
    "app.tasks.analyzers.*": {"queue": "analyze_queue"},
    "app.tasks.validators.*": {"queue": "validate_queue"},
}

# Beat schedule — Beat is a *separate process* that enqueues these task names on cron.
# Workers pick them up from the broker as usual.
celery_app.conf.beat_schedule = {
    "fred-cpi-hourly": {
        "task": "app.tasks.fetchers.fetch_fred_cpi_task",
        # FRED CPI is monthly so polling hourly is overkill — but the spec wants hourly
        # for the general "FRED" cadence (§7.1) and most polls will just be a no-op
        # short-circuited by the (source, external_id) unique check.
        "schedule": crontab(minute=0),
    },
}
