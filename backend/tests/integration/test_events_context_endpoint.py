"""Integration test for GET /api/v1/events/{id} returning context block,
and GET /api/v1/indicators/latest. Hits real Postgres + FastAPI ASGI."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.db.models import (
    DocumentKind,
    Event,
    EventDocument,
    EventSource,
    EventStatus,
    Indicator,
)
from app.main import app


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("DEFAULT_TICKERS", "NVDA,SPY,QQQ")
    monkeypatch.setenv("ANALYZER_LOOKBACK_DAYS", "30")
    monkeypatch.setenv("ANALYZER_RECENT_EVENTS_CAP", "50")
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


async def _seed_event_at(
    db: AsyncSession,
    *,
    external_id: str,
    published_at: datetime,
    event_type: str = "8K_FILING",
) -> Event:
    e = Event(
        source=EventSource.SEC_EDGAR,
        event_type=event_type,
        external_id=external_id,
        title=f"event {external_id}",
        payload={"k": "v"},
        affected_tickers=["NVDA"],
        published_at=published_at,
        fetched_at=published_at,
        status=EventStatus.FETCHED,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _seed_indicator(
    db: AsyncSession, *, key: str, observed_at: datetime, value: float
) -> None:
    db.add(
        Indicator(
            indicator_key=key,
            observed_at=observed_at,
            value=Decimal(str(value)),
            source="FRED",
            payload={},
        )
    )
    await db.commit()


async def test_event_detail_returns_context_block(clean_db: AsyncSession) -> None:
    trigger_at = datetime(2026, 6, 1, 14, 30, tzinfo=UTC)
    trigger = await _seed_event_at(clean_db, external_id="trigger", published_at=trigger_at)
    # A prior event within the 30-day window
    await _seed_event_at(clean_db, external_id="prior", published_at=trigger_at - timedelta(days=5))
    # Indicators: latest + 30d-ago
    await _seed_indicator(
        clean_db, key="DGS10", observed_at=trigger_at - timedelta(days=1), value=4.50
    )
    await _seed_indicator(
        clean_db, key="DGS10", observed_at=trigger_at - timedelta(days=30), value=4.25
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/events/{trigger.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert "context" in body
    ctx = body["context"]
    assert ctx["lookback_days"] == 30

    titles = {e["title"] for e in ctx["recent_events"]}
    assert "event prior" in titles
    assert "event trigger" not in titles  # triggering event excluded

    indicators_by_key = {i["indicator_key"]: i for i in ctx["latest_indicators"]}
    assert "DGS10" in indicators_by_key
    assert indicators_by_key["DGS10"]["value"] == 4.50
    assert indicators_by_key["DGS10"]["delta_30d"] == pytest.approx(0.25)


async def test_event_detail_returns_attached_documents_sorted(
    clean_db: AsyncSession,
) -> None:
    """attached_documents block returns PRESS_RELEASE first, then FILING_COVER."""
    trigger_at = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)
    trigger = await _seed_event_at(
        clean_db, external_id="trigger-with-docs", published_at=trigger_at
    )
    clean_db.add_all(
        [
            EventDocument(
                event_id=trigger.id,
                doc_kind=DocumentKind.FILING_COVER,
                content_text="Item 2.02 - Earnings Results. " * 30,
                raw_url="https://www.sec.gov/.../nvda-8k.htm",
                byte_size=900,
                fetched_at=datetime.now(UTC),
            ),
            EventDocument(
                event_id=trigger.id,
                doc_kind=DocumentKind.PRESS_RELEASE,
                content_text="NVIDIA Reports Q1 Revenue of $81.6B. " * 30,
                raw_url="https://www.sec.gov/.../ex991.htm",
                byte_size=1110,
                fetched_at=datetime.now(UTC),
            ),
        ]
    )
    await clean_db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/events/{trigger.id}")
    assert resp.status_code == 200
    docs = resp.json()["attached_documents"]
    assert len(docs) == 2
    # PRESS_RELEASE sorts first per the API's natural order
    assert docs[0]["doc_kind"] == "PRESS_RELEASE"
    assert docs[1]["doc_kind"] == "FILING_COVER"
    assert "NVIDIA Reports" in docs[0]["content_text"]
    assert docs[0]["byte_size"] == 1110


async def test_event_detail_attached_documents_empty_when_none(
    clean_db: AsyncSession,
) -> None:
    trigger = await _seed_event_at(
        clean_db, external_id="trigger-no-docs", published_at=datetime(2026, 6, 8, tzinfo=UTC)
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/events/{trigger.id}")
    assert resp.status_code == 200
    assert resp.json()["attached_documents"] == []


async def test_event_detail_404_for_unknown_id(clean_db: AsyncSession) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/events/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_indicators_latest_returns_one_row_per_key(
    clean_db: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    # DGS10: two observations — latest should win
    await _seed_indicator(clean_db, key="DGS10", observed_at=now - timedelta(days=2), value=4.40)
    await _seed_indicator(clean_db, key="DGS10", observed_at=now - timedelta(days=32), value=4.10)
    # DGS2: single observation
    await _seed_indicator(clean_db, key="DGS2", observed_at=now - timedelta(days=1), value=4.05)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/indicators/latest")

    assert resp.status_code == 200
    body = resp.json()
    by_key = {i["indicator_key"]: i for i in body["indicators"]}
    assert set(by_key.keys()) == {"DGS10", "DGS2"}
    assert by_key["DGS10"]["value"] == 4.40
    assert by_key["DGS10"]["delta_30d"] == pytest.approx(0.30)
    assert by_key["DGS2"]["delta_30d"] is None  # only one observation


async def test_indicators_latest_empty_table_returns_empty_list(
    clean_db: AsyncSession,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/indicators/latest")
    assert resp.status_code == 200
    assert resp.json() == {"indicators": []}
