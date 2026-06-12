"""Integration tests for the Phase B documents pipeline:
  - document_fetcher.fetch_documents_for_event persists FILING_COVER + PRESS_RELEASE
  - analyzer correctly defers 8-K events <5min old without docs
  - analyzer proceeds when documents exist OR fetched_at is past the wait window

Requires Postgres (docker compose up postgres)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.db.models import (
    DocumentKind,
    Event,
    EventDocument,
    EventSource,
    EventStatus,
)
from app.services.analyzer import _candidate_event_ids
from app.services.document_fetcher import fetch_documents_for_event


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test")
    monkeypatch.setenv("SEC_USER_AGENT", "EventSense-tests test@example.com")
    from app.config.settings import get_settings as _get

    _get.cache_clear()


@pytest_asyncio.fixture
async def clean_db() -> AsyncSession:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_local = async_sessionmaker(engine, expire_on_commit=False)
    async with session_local() as session:
        await session.execute(text("TRUNCATE TABLE events CASCADE"))
        await session.commit()
        yield session
    await engine.dispose()


async def _seed_8k(
    db: AsyncSession,
    *,
    ticker: str = "NVDA",
    accession: str = "0001045810-26-000099",
    fetched_age_minutes: int = 0,
) -> Event:
    now = datetime.now(UTC)
    e = Event(
        source=EventSource.SEC_EDGAR,
        event_type="8K_FILING",
        external_id=accession,
        title=f"{ticker} 8-K filed",
        payload={
            "cik": "0001045810",
            "ticker": ticker,
            "accession_number": accession,
            "filing_date": "2026-06-08",
            "item_codes": "2.02,9.01",
            "primary_doc_url": (
                f"https://www.sec.gov/Archives/edgar/data/1045810/"
                f"{accession.replace('-', '')}/nvda-8k.htm"
            ),
            "company_name": "NVIDIA Corp",
        },
        affected_tickers=[ticker],
        published_at=now,
        fetched_at=now - timedelta(minutes=fetched_age_minutes),
        status=EventStatus.FETCHED,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


_PRIMARY_HTML = (
    "<html><body><div>" + ("Item 2.02 - Earnings Results. " * 30) + "</div></body></html>"
)
_EX99_HTML = (
    "<html><body><p>" + ("NVIDIA Reports Q1 Revenue of $81.6 billion. " * 30) + "</p></body></html>"
)

_FAKE_INDEX_JSON = {
    "directory": {
        "item": [
            {"name": "nvda-8k.htm"},
            {"name": "ex991.htm"},
            {"name": "MetaLinks.json"},
        ]
    }
}


async def test_fetch_documents_for_8k_persists_cover_and_press_release(
    clean_db: AsyncSession,
) -> None:
    event = await _seed_8k(clean_db)

    # Mock the inner HTTP helpers so we don't actually hit SEC.
    async def _fake_fetch_and_strip(_client, url: str) -> str | None:
        if url.endswith("nvda-8k.htm"):
            return "Item 2.02 - Earnings Results. " * 30
        if url.endswith("ex991.htm"):
            return "NVIDIA Reports Q1 Revenue of $81.6 billion. " * 30
        return None

    async def _fake_list_exhibits(_client, _index_url: str) -> list[str]:
        return ["ex991.htm"]

    with (
        patch(
            "app.services.document_fetcher._fetch_and_strip",
            new=AsyncMock(side_effect=_fake_fetch_and_strip),
        ),
        patch(
            "app.services.document_fetcher._list_exhibit_files",
            new=AsyncMock(side_effect=_fake_list_exhibits),
        ),
    ):
        inserted = await fetch_documents_for_event(clean_db, event)

    assert inserted == 2

    docs = (
        await clean_db.scalars(select(EventDocument).where(EventDocument.event_id == event.id))
    ).all()
    by_kind = {d.doc_kind: d for d in docs}
    assert DocumentKind.FILING_COVER in by_kind
    assert DocumentKind.PRESS_RELEASE in by_kind
    assert "Item 2.02" in by_kind[DocumentKind.FILING_COVER].content_text
    assert "NVIDIA Reports" in by_kind[DocumentKind.PRESS_RELEASE].content_text


async def test_fetch_documents_idempotent_via_unique_constraint(
    clean_db: AsyncSession,
) -> None:
    """Re-running fetch_documents for the same event inserts zero (dedup)."""
    event = await _seed_8k(clean_db)

    with (
        patch(
            "app.services.document_fetcher._fetch_and_strip",
            new=AsyncMock(return_value="Item 2.02 - Earnings Results. " * 30),
        ),
        patch(
            "app.services.document_fetcher._list_exhibit_files",
            new=AsyncMock(return_value=[]),
        ),
    ):
        first = await fetch_documents_for_event(clean_db, event)
        second = await fetch_documents_for_event(clean_db, event)

    assert first == 1
    assert second == 0


async def test_fetch_documents_skips_non_8k_events(clean_db: AsyncSession) -> None:
    """Earnings / FRED / FOMC events shouldn't trigger doc fetch."""
    now = datetime.now(UTC)
    earnings = Event(
        source=EventSource.EARNINGS,
        event_type="EARNINGS_REPORT",
        external_id="NVDA:2026-04-30",
        title="x",
        payload={"ticker": "NVDA"},
        affected_tickers=["NVDA"],
        published_at=now,
        fetched_at=now,
        status=EventStatus.FETCHED,
    )
    clean_db.add(earnings)
    await clean_db.commit()
    await clean_db.refresh(earnings)

    inserted = await fetch_documents_for_event(clean_db, earnings)
    assert inserted == 0


async def test_analyzer_defers_recent_8k_without_documents(
    clean_db: AsyncSession,
) -> None:
    """8-K fetched 2 minutes ago with no docs → not in candidate set."""
    await _seed_8k(clean_db, fetched_age_minutes=2)
    candidates = await _candidate_event_ids(clean_db, 100)
    assert candidates == []


async def test_analyzer_picks_up_8k_after_wait_window(clean_db: AsyncSession) -> None:
    """8-K fetched 10 minutes ago with no docs → falls through, gets analyzed."""
    event = await _seed_8k(clean_db, fetched_age_minutes=10)
    candidates = await _candidate_event_ids(clean_db, 100)
    assert event.id in candidates


async def test_analyzer_picks_up_8k_with_documents_even_if_recent(
    clean_db: AsyncSession,
) -> None:
    """8-K fetched 1 minute ago BUT has documents attached → eligible immediately."""
    event = await _seed_8k(clean_db, fetched_age_minutes=1)
    # Pre-attach a document so the wait condition is satisfied.
    clean_db.add(
        EventDocument(
            event_id=event.id,
            doc_kind=DocumentKind.FILING_COVER,
            content_text="x" * 500,
            raw_url="https://example.com/x",
            byte_size=500,
            fetched_at=datetime.now(UTC),
        )
    )
    await clean_db.commit()

    candidates = await _candidate_event_ids(clean_db, 100)
    assert event.id in candidates


async def test_analyzer_never_defers_non_8k_events(clean_db: AsyncSession) -> None:
    """A fresh FRED CPI event should be analyzed immediately — no doc wait."""
    now = datetime.now(UTC)
    cpi = Event(
        source=EventSource.FRED,
        event_type="CPI_RELEASE",
        external_id="CPI:2026-06-08",
        title="CPI",
        payload={"value": 332.0},
        affected_tickers=[],
        published_at=now,
        fetched_at=now,
        status=EventStatus.FETCHED,
    )
    clean_db.add(cpi)
    await clean_db.commit()
    await clean_db.refresh(cpi)

    candidates = await _candidate_event_ids(clean_db, 100)
    assert cpi.id in candidates
