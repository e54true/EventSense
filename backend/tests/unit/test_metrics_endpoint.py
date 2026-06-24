"""Unit tests for the Milestone 11 Prometheus /metrics endpoint.

These run without a database: refresh_domain_metrics() must swallow connection
errors and still let the endpoint serve HTTP + static gauges. The domain gauges
sourced from Postgres are exercised by the integration suite / live stack.
"""

from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST

from app.main import app
from app.observability import metrics


def test_metrics_endpoint_serves_prometheus_text() -> None:
    client = TestClient(app, raise_server_exceptions=False)
    # Drive one instrumented request so an HTTP series exists.
    client.get("/")

    resp = client.get("/metrics")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == CONTENT_TYPE_LATEST
    body = resp.text
    # HTTP RED metrics (from the instrumentator middleware).
    assert "http_request_duration_seconds_bucket" in body
    assert "http_requests_total{" in body
    # Static domain gauge set before the DB query — present even with no DB.
    assert "eventsense_llm_cost_cap_usd" in body


async def test_refresh_domain_metrics_is_db_error_tolerant() -> None:
    # No Postgres in unit-test env → the refresh must not raise, so a scrape
    # never 500s just because the DB is briefly unreachable.
    await metrics.refresh_domain_metrics(force=True)
    # The cap gauge is set before the DB call, so it always reflects settings.
    cap = metrics.get_settings().llm_daily_cost_cap_usd
    assert metrics.LLM_COST_CAP._value.get() == cap
