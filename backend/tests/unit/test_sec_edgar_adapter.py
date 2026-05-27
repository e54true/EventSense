"""Unit tests for SEC EDGAR adapter — parsing column-oriented submissions JSON."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.sec_edgar import _parse_recent_8ks, fetch_new
from app.db.models import EventSource


@pytest.fixture(autouse=True)
def _set_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "EventSense test@example.com")
    from app.config.settings import get_settings

    get_settings.cache_clear()


def _make_submissions(forms: list[str], dates: list[str]) -> dict:
    """Build a fake SEC submissions response with matching parallel arrays."""
    n = len(forms)
    return {
        "name": "Test Corp",
        "filings": {
            "recent": {
                "form": forms,
                "accessionNumber": [f"0000000000-26-{i:06d}" for i in range(n)],
                "filingDate": dates,
                "primaryDocument": [f"doc-{i}.htm" for i in range(n)],
                "items": ["2.02,9.01"] * n,
            }
        },
    }


def test_parse_recent_8ks_filters_to_8k_only() -> None:
    """Non-8-K forms (10-K, 4, etc) must be ignored."""
    today = datetime.now(UTC).date()
    submissions = _make_submissions(
        forms=["8-K", "10-K", "4", "8-K"],
        dates=[today.isoformat()] * 4,
    )
    events = _parse_recent_8ks(submissions, cik="0000320193", ticker="AAPL", cutoff=today)
    assert len(events) == 2
    assert all(e.event_type == "8K_FILING" for e in events)
    assert all(e.affected_tickers == ["AAPL"] for e in events)
    assert all(e.source == EventSource.SEC_EDGAR for e in events)


def test_parse_recent_8ks_drops_old_filings() -> None:
    """Filings older than the cutoff date must be skipped."""
    today = datetime.now(UTC).date()
    submissions = _make_submissions(
        forms=["8-K", "8-K", "8-K"],
        dates=[
            today.isoformat(),
            (today - timedelta(days=20)).isoformat(),  # past cutoff
            (today - timedelta(days=5)).isoformat(),
        ],
    )
    cutoff = today - timedelta(days=14)
    events = _parse_recent_8ks(submissions, cik="0000320193", ticker="AAPL", cutoff=cutoff)
    assert len(events) == 2  # the 20-day-old one is dropped


def test_parse_recent_8ks_builds_correct_doc_url() -> None:
    today = datetime.now(UTC).date()
    submissions = {
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "form": ["8-K"],
                "accessionNumber": ["0000320193-26-000042"],
                "filingDate": [today.isoformat()],
                "primaryDocument": ["aapl-20260415.htm"],
                "items": ["2.02"],
            }
        },
    }
    [event] = _parse_recent_8ks(submissions, cik="0000320193", ticker="AAPL", cutoff=today)
    assert event.payload["primary_doc_url"] == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019326000042/aapl-20260415.htm"
    )


async def test_fetch_new_raises_without_valid_user_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC requires email in User-Agent — bare names must be rejected."""
    monkeypatch.setenv("SEC_USER_AGENT", "MyApp")  # no @
    from app.config.settings import get_settings

    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        await fetch_new()


async def test_fetch_new_continues_after_per_ticker_failure() -> None:
    """If one ticker's CIK is bad (404), the run keeps going for the others."""
    import httpx

    today_iso = datetime.now(UTC).date().isoformat()
    good_response = _make_submissions(forms=["8-K"], dates=[today_iso])

    call_count = {"n": 0}

    async def fake_fetch(_client, _cik):  # underscore signals "intentionally unused"
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First ticker fails with 404
            req = httpx.Request("GET", "https://example")
            resp = httpx.Response(404, request=req)
            raise httpx.HTTPStatusError("404", request=req, response=resp)
        return good_response

    with (
        patch("app.adapters.sec_edgar._fetch_submissions", new=fake_fetch),
        patch("app.adapters.sec_edgar.TICKER_TO_CIK", {"BAD": "0000000000", "AAPL": "0000320193"}),
        patch("app.adapters.sec_edgar.asyncio.sleep", new=AsyncMock()),  # skip rate-limit sleeps
    ):
        events = await fetch_new()

    # First ticker (BAD) failed but AAPL still produced events
    assert len(events) >= 1
    assert events[0].affected_tickers == ["AAPL"]
