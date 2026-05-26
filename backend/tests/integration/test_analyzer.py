"""Integration test for the analyzer state machine.

Validates FETCHED → ANALYZED and FETCHED → FAILED transitions, plus
hallucination filtering. The LLM itself is mocked — we're testing the orchestration,
not OpenAI.

Requires Postgres (docker compose up postgres).
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.db.models import Event, EventSource, EventStatus, Prediction
from app.llm.clients import LLMCallResult
from app.llm.schemas import EventAnalysis, TickerImpact
from app.services.analyzer import analyze_pending


@pytest.fixture(autouse=True)
def _llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_DAILY_COST_CAP_USD", "100.0")
    monkeypatch.setenv("DEFAULT_TICKERS", "AAPL,MSFT,SPY")
    from app.config.settings import get_settings as _get
    _get.cache_clear()


@pytest_asyncio.fixture
async def clean_db() -> AsyncSession:
    """Truncate both events and predictions before each test."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)
    async with session_local() as session:
        # CASCADE wipes child predictions automatically thanks to ondelete=CASCADE.
        await session.execute(text("TRUNCATE TABLE events CASCADE"))
        await session.commit()
        yield session
    await engine.dispose()


async def _seed_event(db: AsyncSession, ticker: str = "AAPL") -> Event:
    e = Event(
        source=EventSource.SEC_EDGAR,
        event_type="8K_FILING",
        external_id=f"test-{ticker}-{datetime.now(UTC).timestamp()}",
        title=f"{ticker} test 8-K",
        payload={"ticker": ticker, "item": "2.02"},
        affected_tickers=[ticker],
        published_at=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
        status=EventStatus.FETCHED,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


def _fake_analysis(ticker: str = "AAPL") -> LLMCallResult:
    return LLMCallResult(
        analysis=EventAnalysis(
            summary="Test event summary.",
            impacts=[
                TickerImpact(
                    ticker=ticker,
                    direction="BULLISH",
                    magnitude="MEDIUM",
                    confidence=0.7,
                    reasoning="Test reasoning.",
                )
            ],
        ),
        prompt_tokens=500,
        completion_tokens=200,
    )


async def test_fetched_event_transitions_to_analyzed_with_predictions(clean_db: AsyncSession) -> None:
    event = await _seed_event(clean_db, "AAPL")

    with patch(
        "app.services.analyzer.clients.analyze_event",
        new=AsyncMock(return_value=_fake_analysis("AAPL")),
    ):
        result = await analyze_pending(clean_db, batch_size=10)

    assert result["events_processed"] == 1
    assert result["predictions_emitted"] == 1
    assert result["skipped_locked"] == 0
    await clean_db.refresh(event)
    assert event.status == EventStatus.ANALYZED
    assert event.failure_reason is None

    pred = await clean_db.scalar(select(Prediction).where(Prediction.event_id == event.id))
    assert pred is not None
    assert pred.ticker == "AAPL"
    assert pred.direction.value == "BULLISH"
    assert pred.llm_cost_usd > 0


async def test_llm_failure_marks_event_failed_with_reason(clean_db: AsyncSession) -> None:
    event = await _seed_event(clean_db, "MSFT")

    async def _boom(*_args, **_kwargs) -> LLMCallResult:
        raise RuntimeError("OpenAI returned 500")

    with patch("app.services.analyzer.clients.analyze_event", new=_boom):
        await analyze_pending(clean_db, batch_size=10)

    await clean_db.refresh(event)
    assert event.status == EventStatus.FAILED
    assert "OpenAI returned 500" in (event.failure_reason or "")
    # No predictions should have been written on the failure path.
    n_preds = await clean_db.scalar(
        select(func.count()).select_from(Prediction).where(Prediction.event_id == event.id)
    )
    assert n_preds == 0


async def test_hallucinated_ticker_is_dropped(clean_db: AsyncSession) -> None:
    """LLM emits a ticker outside the watchlist → that impact gets silently dropped."""
    await _seed_event(clean_db, "AAPL")

    bad_analysis = LLMCallResult(
        analysis=EventAnalysis(
            summary="x",
            impacts=[
                TickerImpact(ticker="AAPL", direction="BULLISH", magnitude="LOW", confidence=0.5, reasoning="ok"),
                TickerImpact(ticker="HALUC", direction="BEARISH", magnitude="HIGH", confidence=0.9, reasoning="bad"),
            ],
        ),
        prompt_tokens=500,
        completion_tokens=200,
    )
    with patch("app.services.analyzer.clients.analyze_event", new=AsyncMock(return_value=bad_analysis)):
        result = await analyze_pending(clean_db, batch_size=10)

    assert result["predictions_emitted"] == 1  # HALUC dropped
    tickers = {p.ticker for p in (await clean_db.scalars(select(Prediction))).all()}
    assert tickers == {"AAPL"}


async def test_analyzer_only_picks_fetched_status(clean_db: AsyncSession) -> None:
    """Events with status != FETCHED must be ignored — protects against reprocessing."""
    already_analyzed = await _seed_event(clean_db, "AAPL")
    already_analyzed.status = EventStatus.ANALYZED
    await clean_db.commit()

    with patch(
        "app.services.analyzer.clients.analyze_event",
        new=AsyncMock(return_value=_fake_analysis()),
    ) as mock_llm:
        result = await analyze_pending(clean_db, batch_size=10)

    assert result["events_processed"] == 0
    assert mock_llm.call_count == 0
