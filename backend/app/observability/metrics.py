"""Prometheus metrics — HTTP request metrics + domain gauges.

Three layers make up EventSense's observability story:

  1. HTTP (RED metrics) — prometheus-fastapi-instrumentator adds ASGI
     middleware that records request count / latency histogram / in-progress
     gauge per (method, handler, status). We call only `.instrument(app)` here,
     NOT `.expose()`: the /metrics route is defined by hand in app.main so it can
     be `async` and await the domain refresh below.

  2. Domain — gauges that mirror business state: the event pipeline funnel
     (events by source x status), prediction volume, directional accuracy per
     outcome window, and today's LLM spend against the daily cap. These are
     refreshed by querying Postgres at scrape time, behind a short TTL cache so
     a tight Prometheus scrape interval doesn't turn into a DB hammer.

  3. Celery — task throughput / failures / runtime. NOT here: those are scraped
     out-of-process by the celery-exporter container, which listens to the
     broker's task-event stream. Workers run as separate processes, so their
     counters would never show up in this API process's registry anyway.

Why scrape-time refresh instead of incrementing counters in code paths? The
analyzer / validator run inside Celery workers, a different process from the
API that serves /metrics. A counter incremented there is invisible here. Gauges
sourced from the shared source of truth (Postgres) sidestep cross-process
aggregation entirely — the DB is the one place every process already agrees on.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import FastAPI
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import func, select

from app.config.settings import get_settings
from app.db.models import Event, Prediction, PredictionOutcome
from app.db.session import AsyncSessionLocal

# --- Domain gauges -----------------------------------------------------------
# Naming follows Prometheus convention: <namespace>_<subsystem>_<unit>, base
# units (seconds / dollars), no plural "s" suffix on the metric name itself.

EVENTS = Gauge(
    "eventsense_events",
    "Number of ingested events, partitioned by source and pipeline status.",
    ["source", "status"],
)
PREDICTIONS_TOTAL = Gauge(
    "eventsense_predictions_total",
    "Total number of LLM predictions generated.",
)
OUTCOMES_TOTAL = Gauge(
    "eventsense_outcomes_total",
    "Validated prediction outcomes, partitioned by window and alignment.",
    ["window", "aligned"],
)
DIRECTIONAL_ACCURACY = Gauge(
    "eventsense_directional_accuracy",
    "Share of validated outcomes whose direction was correct (0..1), per window.",
    ["window"],
)
LLM_COST_TODAY = Gauge(
    "eventsense_llm_cost_today_usd",
    "Accumulated LLM spend (USD) since 00:00 UTC today.",
)
LLM_COST_CAP = Gauge(
    "eventsense_llm_cost_cap_usd",
    "Configured hard daily LLM spend cap (USD).",
)

# Scrape-time refresh is cached for this long so frequent Prometheus scrapes
# (default 15s) don't issue a fresh round of aggregate queries every time.
_REFRESH_TTL_SECONDS = 10.0
_last_refresh_at: float = 0.0


def setup_instrumentation(app: FastAPI) -> None:
    """Attach the HTTP-metrics middleware to the FastAPI app.

    Only the middleware is registered (not the /metrics route) — see module
    docstring. Safe to call once at import/startup.
    """
    Instrumentator(
        should_group_status_codes=False,  # keep 200 vs 201 vs 503 distinct
        excluded_handlers=["/metrics", "/health"],  # don't measure the probes
    ).instrument(app)


async def refresh_domain_metrics(*, force: bool = False) -> None:
    """Re-query Postgres and update the domain gauges, behind a TTL cache.

    Called by the /metrics handler before serializing the registry. `force`
    bypasses the cache (used in tests). Any DB error is swallowed: a metrics
    endpoint must never 500 — Prometheus would just record a scrape failure,
    but we'd rather serve stale-but-valid numbers and keep HTTP metrics flowing.
    """
    global _last_refresh_at
    now = time.monotonic()
    if not force and (now - _last_refresh_at) < _REFRESH_TTL_SECONDS:
        return

    settings = get_settings()
    LLM_COST_CAP.set(settings.llm_daily_cost_cap_usd)

    try:
        async with AsyncSessionLocal() as session:
            # 1) Event pipeline funnel: source x status counts.
            EVENTS.clear()  # drop stale label sets (e.g. a status that emptied out)
            event_rows = await session.execute(
                select(Event.source, Event.status, func.count()).group_by(
                    Event.source, Event.status
                )
            )
            for source, status, count in event_rows:
                EVENTS.labels(source=str(source), status=str(status)).set(count)

            # 2) Prediction volume.
            pred_total = await session.scalar(select(func.count()).select_from(Prediction))
            PREDICTIONS_TOTAL.set(pred_total or 0)

            # 3) Outcomes + directional accuracy, per window. `aligned` is the
            #    canonical correctness flag the validator writes.
            OUTCOMES_TOTAL.clear()
            outcome_rows = (
                await session.execute(
                    select(
                        PredictionOutcome.window,
                        PredictionOutcome.aligned,
                        func.count(),
                    ).group_by(PredictionOutcome.window, PredictionOutcome.aligned)
                )
            ).all()
            per_window: dict[str, dict[bool, int]] = {}
            for window, aligned, count in outcome_rows:
                w = str(window)
                OUTCOMES_TOTAL.labels(window=w, aligned=str(aligned).lower()).set(count)
                per_window.setdefault(w, {})[bool(aligned)] = count
            for w, buckets in per_window.items():
                hits = buckets.get(True, 0)
                total = hits + buckets.get(False, 0)
                DIRECTIONAL_ACCURACY.labels(window=w).set(hits / total if total else 0.0)

            # 4) Today's LLM spend (matches the daily-cap story; gauge vs cap).
            midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            cost_today = await session.scalar(
                select(func.coalesce(func.sum(Prediction.llm_cost_usd), 0.0)).where(
                    Prediction.predicted_at >= midnight
                )
            )
            LLM_COST_TODAY.set(float(cost_today or 0.0))
    except Exception:  # pragma: no cover - defensive; see docstring
        # Leave gauges at their previous values; never break the scrape.
        return

    _last_refresh_at = now
