"""Observability (Milestone 11) — Prometheus metrics for the FastAPI app.

See app.observability.metrics for the metric definitions and the scrape-time
domain refresh. Celery task metrics are scraped out-of-process by the
celery-exporter container (docker-compose), not from here.
"""
