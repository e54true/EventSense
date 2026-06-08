"""Integration test for the v2 contextual analyzer.

Exercises:
  - MARKET impacts (SPY/QQQ) emitted for any event type
  - COMPANY impacts emitted ONLY for company-specific events (8-K, earnings)
  - kind=MARKET with non-{SPY,QQQ} ticker is rejected
  - kind=COMPANY with off-target ticker is rejected
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.db.models import (
    Event,
    EventSource,
    EventStatus,
    Prediction,
    PredictionKind,
)
from app.llm.clients import LLMCallResult
from app.llm.schemas import EventAnalysis, TickerImpact
from app.services.analyzer import analyze_pending


@pytest.fixture(autouse=True)
def _llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_DAILY_COST_CAP_USD", "100.0")
    monkeypatch.setenv("DEFAULT_TICKERS", "NVDA,AAPL,SPY,QQQ")
    monkeypatch.setenv("ANALYZER_PROMPT_VERSION", "v2")
    monkeypatch.setenv("FRED_API_KEY", "test")
    from app.config.settings import get_settings as _get

    _get.cache_clear()


@pytest_asyncio.fixture
async def clean_db() -> AsyncSession:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)
    async with session_local() as session:
        await session.execute(text("TRUNCATE TABLE events CASCADE"))
        await session.execute(text("TRUNCATE TABLE indicators"))
        await session.commit()
        yield session
    await engine.dispose()


async def _seed_event(
    db: AsyncSession,
    *,
    source: EventSource,
    event_type: str,
    ticker: str | None,
) -> Event:
    e = Event(
        source=source,
        event_type=event_type,
        external_id=f"{event_type}-{datetime.now(UTC).timestamp()}",
        title=f"{event_type} for {ticker or 'macro'}",
        payload={"ticker": ticker} if ticker else {},
        affected_tickers=[ticker] if ticker else [],
        published_at=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
        status=EventStatus.FETCHED,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


def _wrap(impacts: list[TickerImpact]) -> LLMCallResult:
    return LLMCallResult(
        analysis=EventAnalysis(summary="test", impacts=impacts),
        prompt_tokens=500,
        completion_tokens=200,
    )


async def test_v2_emits_market_and_company_impacts_for_company_event(
    clean_db: AsyncSession,
) -> None:
    """8-K for NVDA → analyzer should accept [MARKET SPY, MARKET QQQ, COMPANY NVDA]."""
    event = await _seed_event(
        clean_db, source=EventSource.SEC_EDGAR, event_type="8K_FILING", ticker="NVDA"
    )

    impacts = [
        TickerImpact(
            ticker="SPY", kind="MARKET", direction="BULLISH", magnitude="LOW",
            confidence=0.55, reasoning="Macro tailwind.",
        ),
        TickerImpact(
            ticker="QQQ", kind="MARKET", direction="BULLISH", magnitude="MEDIUM",
            confidence=0.6, reasoning="Tech-heavy index reacts to NVDA.",
        ),
        TickerImpact(
            ticker="NVDA", kind="COMPANY", direction="BULLISH", magnitude="HIGH",
            confidence=0.75, reasoning="Strong filing.",
        ),
    ]
    with patch(
        "app.services.analyzer.clients.analyze_event",
        new=AsyncMock(return_value=_wrap(impacts)),
    ):
        result = await analyze_pending(clean_db, batch_size=10)

    assert result["predictions_emitted"] == 3
    rows = (
        await clean_db.scalars(select(Prediction).where(Prediction.event_id == event.id))
    ).all()
    by_ticker = {p.ticker: p for p in rows}
    assert by_ticker["SPY"].kind == PredictionKind.MARKET
    assert by_ticker["QQQ"].kind == PredictionKind.MARKET
    assert by_ticker["NVDA"].kind == PredictionKind.COMPANY


async def test_v2_drops_company_impact_on_macro_event(clean_db: AsyncSession) -> None:
    """CPI release → COMPANY NVDA impact should be rejected (only MARKET allowed)."""
    await _seed_event(
        clean_db, source=EventSource.FRED, event_type="CPI_RELEASE", ticker=None
    )

    impacts = [
        TickerImpact(
            ticker="SPY", kind="MARKET", direction="BEARISH", magnitude="MEDIUM",
            confidence=0.6, reasoning="Hot print.",
        ),
        TickerImpact(
            ticker="NVDA", kind="COMPANY", direction="BEARISH", magnitude="MEDIUM",
            confidence=0.6, reasoning="Should not be allowed.",
        ),
    ]
    with patch(
        "app.services.analyzer.clients.analyze_event",
        new=AsyncMock(return_value=_wrap(impacts)),
    ):
        result = await analyze_pending(clean_db, batch_size=10)

    assert result["predictions_emitted"] == 1  # only the MARKET SPY
    tickers = {p.ticker for p in (await clean_db.scalars(select(Prediction))).all()}
    assert tickers == {"SPY"}


async def test_v2_drops_market_impact_with_bad_ticker(clean_db: AsyncSession) -> None:
    """kind=MARKET with ticker=NVDA → reject (only SPY/QQQ allowed)."""
    await _seed_event(
        clean_db, source=EventSource.FOMC, event_type="FOMC_STATEMENT", ticker=None
    )
    impacts = [
        TickerImpact(
            ticker="NVDA", kind="MARKET", direction="BULLISH", magnitude="LOW",
            confidence=0.5, reasoning="oops",
        ),
        TickerImpact(
            ticker="SPY", kind="MARKET", direction="BULLISH", magnitude="LOW",
            confidence=0.5, reasoning="ok",
        ),
    ]
    with patch(
        "app.services.analyzer.clients.analyze_event",
        new=AsyncMock(return_value=_wrap(impacts)),
    ):
        result = await analyze_pending(clean_db, batch_size=10)
    assert result["predictions_emitted"] == 1


async def test_v2_drops_company_impact_off_target(clean_db: AsyncSession) -> None:
    """8-K affected=[NVDA] but LLM emits COMPANY AAPL → reject (off-target spillover)."""
    await _seed_event(
        clean_db, source=EventSource.SEC_EDGAR, event_type="8K_FILING", ticker="NVDA"
    )
    impacts = [
        TickerImpact(
            ticker="AAPL", kind="COMPANY", direction="BEARISH", magnitude="LOW",
            confidence=0.4, reasoning="spillover",
        ),
        TickerImpact(
            ticker="NVDA", kind="COMPANY", direction="BULLISH", magnitude="HIGH",
            confidence=0.8, reasoning="ok",
        ),
    ]
    with patch(
        "app.services.analyzer.clients.analyze_event",
        new=AsyncMock(return_value=_wrap(impacts)),
    ):
        result = await analyze_pending(clean_db, batch_size=10)
    assert result["predictions_emitted"] == 1
    tickers = {p.ticker for p in (await clean_db.scalars(select(Prediction))).all()}
    assert tickers == {"NVDA"}
