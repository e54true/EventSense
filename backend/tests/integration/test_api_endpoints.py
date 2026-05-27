"""End-to-end API tests via httpx.AsyncClient + ASGITransport.

We can't use FastAPI's sync TestClient: it spawns a thread / event loop, but
our SQLAlchemy engine pools connections bound to a different loop. That
mismatch raises "got Future attached to a different loop" (same root cause
as M5 — see analyzer notes). The async httpx client runs in the same loop
as the app under test, so the pool stays consistent.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.db.models import (
    Event,
    EventSource,
    EventStatus,
    OutcomeWindow,
    Prediction,
    PredictionDirection,
    PredictionMagnitude,
    PredictionOutcome,
    PriceSnapshot,
)
from app.db.session import get_db, transient_session
from app.main import app


# Override the get_db dependency app-wide so every route under test uses a
# fresh NullPool session bound to the current test's event loop. Without this,
# the module-level pooled engine in app/db/session.py holds asyncpg connections
# bound to the loop that opened them — exactly the M3 / M5 bug, in API form.
async def _test_db():  # type: ignore[no-untyped-def]
    async with transient_session() as session:
        yield session


app.dependency_overrides[get_db] = _test_db


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_TICKERS", "AAPL,SPY")
    from app.config.settings import get_settings as _get

    _get.cache_clear()


@pytest_asyncio.fixture
async def seeded_db() -> AsyncSession:
    """Wipe + seed an event, a prediction, an outcome, and a few prices."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)
    async with session_local() as session:
        await session.execute(text("TRUNCATE TABLE events CASCADE"))
        await session.execute(text("TRUNCATE TABLE price_snapshots"))
        await session.commit()

        # Event + prediction + outcome
        event = Event(
            source=EventSource.SEC_EDGAR,
            event_type="8K_FILING",
            external_id="test-AAPL-api",
            title="AAPL test for API",
            payload={"ticker": "AAPL"},
            affected_tickers=["AAPL"],
            published_at=datetime(2026, 5, 20, 14, 0, tzinfo=UTC),
            fetched_at=datetime(2026, 5, 20, 14, 5, tzinfo=UTC),
            status=EventStatus.ANALYZED,
        )
        session.add(event)
        await session.flush()

        prediction = Prediction(
            event_id=event.id,
            ticker="AAPL",
            direction=PredictionDirection.BULLISH,
            magnitude=PredictionMagnitude.MEDIUM,
            confidence=0.7,
            reasoning="test reasoning",
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            prompt_version="v1",
            llm_cost_usd=0.0001,
            predicted_at=datetime(2026, 5, 20, 14, 30, tzinfo=UTC),
        )
        session.add(prediction)
        await session.flush()

        outcome = PredictionOutcome(
            prediction_id=prediction.id,
            window=OutcomeWindow.H24,
            baseline_price=Decimal("180.00"),
            end_price=Decimal("182.00"),
            ticker_return=0.0111,
            spy_return=0.005,
            excess_return=0.0061,
            aligned=True,
            validated_at=datetime(2026, 5, 21, 15, 0, tzinfo=UTC),
        )
        session.add(outcome)

        # Price snapshots for AAPL across a few minutes
        base_time = datetime(2026, 5, 20, 14, 0, tzinfo=UTC)
        for i in range(5):
            session.add(
                PriceSnapshot(
                    ticker="AAPL",
                    snapshot_at=base_time + timedelta(minutes=i),
                    price=Decimal(f"180.{i:02d}00"),
                    source="yfinance",
                )
            )
        await session.commit()
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """ASGI client that talks to the FastAPI app in the same event loop as the test."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- /events ---


async def test_list_events_returns_paginated_shape(
    seeded_db: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/api/v1/events?per_page=10")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body and "meta" in body
    assert body["meta"]["per_page"] == 10
    assert body["meta"]["total"] >= 1


async def test_get_event_includes_predictions_and_outcomes(
    seeded_db: AsyncSession, client: AsyncClient
) -> None:
    """The nested 1+1+1 selectinload chain should produce predictions[].outcomes[]."""
    events = (await client.get("/api/v1/events")).json()
    event_id = events["data"][0]["id"]
    detail = (await client.get(f"/api/v1/events/{event_id}")).json()

    assert "predictions" in detail
    assert len(detail["predictions"]) == 1
    pred = detail["predictions"][0]
    assert pred["ticker"] == "AAPL"
    # The headline assertion: outcomes are nested under each prediction.
    assert "outcomes" in pred
    assert len(pred["outcomes"]) == 1
    outcome = pred["outcomes"][0]
    assert outcome["window"] == "24h"
    assert outcome["aligned"] is True


async def test_get_event_404(seeded_db: AsyncSession, client: AsyncClient) -> None:
    response = await client.get("/api/v1/events/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# --- /accuracy ---


async def test_accuracy_returns_alignment_rate(
    seeded_db: AsyncSession, client: AsyncClient
) -> None:
    body = (await client.get("/api/v1/accuracy")).json()
    assert body["total_outcomes"] == 1
    assert body["aligned_count"] == 1
    assert body["alignment_rate"] == 1.0


async def test_accuracy_empty_returns_null_rate(
    seeded_db: AsyncSession, client: AsyncClient
) -> None:
    """Filter to a ticker that has no outcomes — alignment_rate must be None."""
    body = (await client.get("/api/v1/accuracy?ticker=NOTHING")).json()
    assert body["total_outcomes"] == 0
    assert body["alignment_rate"] is None


# --- /prices ---


async def test_price_range_returns_ascending_points(
    seeded_db: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get(
        "/api/v1/prices/AAPL/range",
        params={
            "from_at": "2026-05-20T13:55:00Z",
            "to_at": "2026-05-20T14:10:00Z",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert len(body["points"]) == 5
    # Verify ascending order
    timestamps = [p["snapshot_at"] for p in body["points"]]
    assert timestamps == sorted(timestamps)


async def test_price_range_rejects_wide_window(
    seeded_db: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get(
        "/api/v1/prices/AAPL/range",
        params={
            "from_at": "2025-01-01T00:00:00Z",
            "to_at": "2026-05-20T14:10:00Z",
        },
    )
    assert response.status_code == 400


async def test_price_range_404_for_unknown_ticker(
    seeded_db: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get(
        "/api/v1/prices/UNKNOWN/range",
        params={
            "from_at": "2026-05-20T13:55:00Z",
            "to_at": "2026-05-20T14:10:00Z",
        },
    )
    assert response.status_code == 404
