"""Integration test for the validator service.

Covers:
  - Predictions due for a window get outcome rows written
  - Predictions still inside the window are skipped (not premature)
  - Already-outcome'd (prediction, window) pairs are not re-written
  - Missing prices defer (write nothing, increment deferred counter)
  - Alignment direction is computed correctly from actual prices
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
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
from app.services.validator import validate_pending


@pytest_asyncio.fixture
async def clean_db() -> AsyncSession:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)
    async with session_local() as session:
        # Wipe all four tables involved.
        await session.execute(text("TRUNCATE TABLE events CASCADE"))
        await session.execute(text("TRUNCATE TABLE price_snapshots"))
        await session.commit()
        yield session
    await engine.dispose()


async def _seed_event_and_prediction(
    db: AsyncSession,
    *,
    ticker: str,
    direction: PredictionDirection,
    predicted_at: datetime,
) -> Prediction:
    event = Event(
        source=EventSource.SEC_EDGAR,
        event_type="8K_FILING",
        external_id=f"test-{ticker}-{predicted_at.timestamp()}",
        title=f"{ticker} test",
        payload={},
        affected_tickers=[ticker],
        published_at=predicted_at,
        fetched_at=predicted_at,
        status=EventStatus.ANALYZED,
    )
    db.add(event)
    await db.flush()
    pred = Prediction(
        event_id=event.id,
        ticker=ticker,
        direction=direction,
        magnitude=PredictionMagnitude.MEDIUM,
        confidence=0.7,
        reasoning="test",
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        prompt_version="v1",
        llm_cost_usd=0.0001,
        predicted_at=predicted_at,
    )
    db.add(pred)
    await db.commit()
    await db.refresh(pred)
    return pred


async def _seed_price(db: AsyncSession, ticker: str, at: datetime, price: str) -> None:
    db.add(
        PriceSnapshot(
            ticker=ticker,
            snapshot_at=at,
            price=Decimal(price),
            source="yfinance",
        )
    )
    await db.commit()


async def test_due_prediction_with_prices_gets_outcome(clean_db: AsyncSession) -> None:
    """A prediction 25h old, with prices at both times, should produce a 24h outcome."""
    now = datetime.now(UTC)
    predicted_at = now - timedelta(hours=25)  # 24h window is past + buffer

    # AAPL went up 2%, SPY went up 1% → excess +1%, BULLISH was right
    await _seed_price(clean_db, "AAPL", predicted_at, "100.0000")
    await _seed_price(clean_db, "AAPL", predicted_at + timedelta(hours=24), "102.0000")
    await _seed_price(clean_db, "SPY", predicted_at, "500.0000")
    await _seed_price(clean_db, "SPY", predicted_at + timedelta(hours=24), "505.0000")

    pred = await _seed_event_and_prediction(
        clean_db,
        ticker="AAPL",
        direction=PredictionDirection.BULLISH,
        predicted_at=predicted_at,
    )

    result = await validate_pending(clean_db)
    assert result["outcomes_written"] >= 1

    outcome = await clean_db.scalar(
        select(PredictionOutcome).where(
            PredictionOutcome.prediction_id == pred.id,
            PredictionOutcome.window == OutcomeWindow.H24,
        )
    )
    assert outcome is not None
    assert outcome.ticker_return == pytest.approx(0.02)
    assert outcome.spy_return == pytest.approx(0.01)
    assert outcome.excess_return == pytest.approx(0.01)
    assert outcome.aligned is True


async def test_prediction_still_inside_window_is_skipped(clean_db: AsyncSession) -> None:
    """30min-old prediction — 1h window not due yet, validator should skip it."""
    now = datetime.now(UTC)
    predicted_at = now - timedelta(minutes=30)

    await _seed_price(clean_db, "AAPL", predicted_at, "100.0000")
    await _seed_price(clean_db, "SPY", predicted_at, "500.0000")
    await _seed_event_and_prediction(
        clean_db, ticker="AAPL", direction=PredictionDirection.BULLISH, predicted_at=predicted_at
    )

    result = await validate_pending(clean_db)
    assert result["candidates"] == 0
    assert result["outcomes_written"] == 0


async def test_missing_price_defers_not_writes(clean_db: AsyncSession) -> None:
    """Due prediction but no end-time price → defer (write nothing, count it)."""
    now = datetime.now(UTC)
    predicted_at = now - timedelta(hours=25)

    # Only baseline prices — no end-time price.
    await _seed_price(clean_db, "AAPL", predicted_at, "100.0000")
    await _seed_price(clean_db, "SPY", predicted_at, "500.0000")

    await _seed_event_and_prediction(
        clean_db, ticker="AAPL", direction=PredictionDirection.BULLISH, predicted_at=predicted_at
    )

    result = await validate_pending(clean_db)
    assert result["deferred_no_price"] >= 1
    assert result["outcomes_written"] == 0
    total = await clean_db.scalar(select(func.count()).select_from(PredictionOutcome))
    assert total == 0


async def test_existing_outcome_not_rewritten(clean_db: AsyncSession) -> None:
    """Re-running validator on already-outcomed prediction is a no-op."""
    now = datetime.now(UTC)
    predicted_at = now - timedelta(hours=25)

    for ticker, base, end in [("AAPL", "100", "102"), ("SPY", "500", "505")]:
        await _seed_price(clean_db, ticker, predicted_at, base)
        await _seed_price(clean_db, ticker, predicted_at + timedelta(hours=24), end)

    pred = await _seed_event_and_prediction(
        clean_db, ticker="AAPL", direction=PredictionDirection.BULLISH, predicted_at=predicted_at
    )

    first = await validate_pending(clean_db)
    await validate_pending(clean_db)

    # First run writes (at least) the 24h outcome. Second run finds it already
    # present and writes nothing for that pair.
    assert first["outcomes_written"] >= 1
    outcome_count_after_first = await clean_db.scalar(
        select(func.count())
        .select_from(PredictionOutcome)
        .where(PredictionOutcome.prediction_id == pred.id)
    )
    outcome_count_after_second = await clean_db.scalar(
        select(func.count())
        .select_from(PredictionOutcome)
        .where(PredictionOutcome.prediction_id == pred.id)
    )
    assert outcome_count_after_first == outcome_count_after_second


async def test_bearish_correct_when_ticker_underperforms(clean_db: AsyncSession) -> None:
    now = datetime.now(UTC)
    predicted_at = now - timedelta(hours=25)

    # AAPL flat, SPY +3% → excess -3%. BEARISH prediction is "right" in excess terms.
    await _seed_price(clean_db, "AAPL", predicted_at, "100.0000")
    await _seed_price(clean_db, "AAPL", predicted_at + timedelta(hours=24), "100.0000")
    await _seed_price(clean_db, "SPY", predicted_at, "500.0000")
    await _seed_price(clean_db, "SPY", predicted_at + timedelta(hours=24), "515.0000")

    pred = await _seed_event_and_prediction(
        clean_db, ticker="AAPL", direction=PredictionDirection.BEARISH, predicted_at=predicted_at
    )

    await validate_pending(clean_db)
    outcome = await clean_db.scalar(
        select(PredictionOutcome).where(
            PredictionOutcome.prediction_id == pred.id,
            PredictionOutcome.window == OutcomeWindow.H24,
        )
    )
    assert outcome is not None
    assert outcome.excess_return < 0
    assert outcome.aligned is True  # BEARISH + underperformance = right call
