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
    include=[
        "app.tasks.fetchers",
        "app.tasks.prices",
        "app.tasks.analyzers",
        "app.tasks.validators",
        "app.tasks.indicators",
    ],
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
    "app.tasks.prices.*": {"queue": "fetch_queue"},  # prices are I/O-bound like fetchers
    "app.tasks.indicators.*": {"queue": "fetch_queue"},  # indicators are HTTP fetches too
    "app.tasks.analyzers.*": {"queue": "analyze_queue"},
    # Validators have their own queue name (per spec §8) but the existing
    # fetch worker also listens to it — see docker-compose.yml. Keeps queue
    # naming clean for future scaling without sprouting more containers now.
    "app.tasks.validators.*": {"queue": "validate_queue"},
}

# Beat schedule — Beat is a *separate process* that enqueues these task names on cron.
# Workers pick them up from the broker as usual.
celery_app.conf.beat_schedule = {
    "fred-events-hourly": {
        # Task name kept as `fetch_fred_cpi_task` for back-compat with Beat's
        # persisted schedule; the body now covers CPI + NFP + GDP via the
        # multi-series FRED_EVENT_SERIES registry.
        "task": "app.tasks.fetchers.fetch_fred_cpi_task",
        # All three series release monthly/quarterly — hourly polling is overkill
        # but (source, external_id) dedup makes most polls a free no-op.
        "schedule": crontab(minute=0),
    },
    "fred-indicators-daily": {
        "task": "app.tasks.indicators.fetch_fred_indicators_task",
        # DGS10 / DGS2 refresh daily around 16:00 ET (after Treasury auctions
        # close); FRED republishes ~21:00 UTC. 22:15 UTC catches the fresh value.
        "schedule": crontab(hour=22, minute=15),
    },
    "sec-edgar-15min": {
        "task": "app.tasks.fetchers.fetch_sec_edgar_task",
        # Every 15 minutes per spec §7.2. We poll many tickers per run, but each call
        # is cheap (~50KB JSON) and the (source, external_id) dedup makes repeats free.
        "schedule": crontab(minute="*/15"),
    },
    "fomc-daily": {
        "task": "app.tasks.fetchers.fetch_fomc_task",
        # FOMC press releases are rare (~8 scheduled meetings/year + ad hoc). Daily
        # poll is enough; spec §7.3 also calls for tighter cadence on known decision
        # days but that's left for a future milestone.
        "schedule": crontab(hour=14, minute=30),  # 2:30 PM UTC
    },
    "earnings-daily": {
        "task": "app.tasks.fetchers.fetch_earnings_task",
        # Most earnings drop after market close (~4:30 PM ET = 20:30 UTC winter / 21:30 summer).
        # Run at 22:00 UTC to comfortably catch both, with idempotent dedup.
        "schedule": crontab(hour=22, minute=0),
    },
    "prices-5min": {
        "task": "app.tasks.prices.fetch_prices_task",
        # Fires every 5 min unconditionally; the task itself early-returns when
        # market is closed (handling DST without cron gymnastics).
        "schedule": crontab(minute="*/5"),
    },
    "analyzer-1min": {
        "task": "app.tasks.analyzers.analyze_pending_task",
        # Aggressive: every minute, look for FETCHED events that haven't been
        # analyzed yet. Spec §11 M5 acceptance is "every new event automatically
        # gets predictions within 2 minutes" — 1-min cadence comfortably meets it.
        # No-op (immediate return) when nothing pending, so cost is trivial.
        "schedule": crontab(minute="*"),
    },
    "validator-5min": {
        "task": "app.tasks.validators.validate_pending_task",
        # Outcomes naturally lag: 1h window can't be filled before now-1h. There's
        # no urgency to validate immediately — 5-min cadence keeps load light and
        # still backfills outcomes within a tight SLA.
        "schedule": crontab(minute="*/5"),
    },
}
