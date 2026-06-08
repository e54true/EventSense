"""Unit tests for FOMC adapter — RSS parsing + title filtering + body extraction."""

from unittest.mock import AsyncMock, patch
from xml.etree import ElementTree as ET  # test-only: building fake feed input

from app.adapters.fomc import (
    _extract_statement_text,
    _is_fomc_statement,
    _item_to_raw_event,
    fetch_new,
)
from app.db.models import EventSource


def test_is_fomc_statement_matches_common_titles() -> None:
    assert _is_fomc_statement("Federal Reserve issues FOMC statement")
    assert _is_fomc_statement("FOMC statement")
    assert _is_fomc_statement("FOMC issues policy statement")
    # Case-insensitive
    assert _is_fomc_statement("fomc statement (revised)")


def test_is_fomc_statement_rejects_non_fomc() -> None:
    assert not _is_fomc_statement("Beige Book published")
    assert not _is_fomc_statement("Chair Powell testimony")
    assert not _is_fomc_statement("Press conference following FOMC meeting")  # close but not stmt


def test_item_to_raw_event_parses_well_formed_item() -> None:
    xml = """
    <item>
      <title>Federal Reserve issues FOMC statement</title>
      <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260318a.htm</link>
      <description>The FOMC decided today to maintain the target range...</description>
      <pubDate>Wed, 18 Mar 2026 18:00:00 GMT</pubDate>
    </item>
    """
    item = ET.fromstring(xml)
    event = _item_to_raw_event(item)
    assert event is not None
    assert event.source == EventSource.FOMC
    assert event.event_type == "FOMC_STATEMENT"
    assert event.external_id == event.payload["link"]
    assert "maintain the target range" in event.payload["description"]
    assert event.published_at.year == 2026


def test_item_to_raw_event_skips_non_fomc_titles() -> None:
    xml = """
    <item>
      <title>Chair Powell speaks at Jackson Hole</title>
      <link>https://www.federalreserve.gov/newsevents/speech/powell20260824.htm</link>
      <description>...</description>
      <pubDate>Fri, 24 Aug 2026 14:00:00 GMT</pubDate>
    </item>
    """
    assert _item_to_raw_event(ET.fromstring(xml)) is None


def test_item_to_raw_event_skips_missing_pub_date() -> None:
    # FOMC title but missing pubDate — can't determine published_at
    xml = """
    <item>
      <title>FOMC statement</title>
      <link>https://example.com/x</link>
      <description>...</description>
    </item>
    """
    assert _item_to_raw_event(ET.fromstring(xml)) is None


_SAMPLE_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>FRB: Press Releases - Monetary Policy</title>
    <item>
      <title>Federal Reserve issues FOMC statement</title>
      <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260318a.htm</link>
      <description>...maintained...</description>
      <pubDate>Wed, 18 Mar 2026 18:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Beige Book - March 2026</title>
      <link>https://www.federalreserve.gov/monetarypolicy/beigebook202603.htm</link>
      <description>Beige book...</description>
      <pubDate>Wed, 05 Mar 2026 19:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


async def test_fetch_new_extracts_only_fomc_items() -> None:
    """fetch_new now also fetches body per item — patch that too so the test
    doesn't hit the real Fed website."""
    with (
        patch("app.adapters.fomc._fetch_feed_xml", new=AsyncMock(return_value=_SAMPLE_FEED)),
        patch("app.adapters.fomc._fetch_statement_body", new=AsyncMock(return_value=None)),
    ):
        events = await fetch_new()

    assert len(events) == 1
    assert events[0].source == EventSource.FOMC
    assert "FOMC" in events[0].title


# ---- Phase C: body extraction from press release HTML ----


_REAL_FED_PAGE_HTML = """
<html><body>
<header>nav stuff</header>
<div id="article">
<h2>April 29, 2026</h2>
<h3>Federal Reserve issues FOMC statement</h3>
<p>For release at 2:00 p.m. EDT</p>
<p>Recent indicators suggest that economic activity has been expanding at a solid pace. Job gains have remained low, on average, and the unemployment rate has been little changed in recent months. Inflation is elevated, in part reflecting the recent increase in global energy prices.</p>
<p>The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run. In support of its goals, the Committee decided to maintain the target range for the federal funds rate at 3-1/2 to 3-3/4 percent.</p>
</div>
<footer>boilerplate</footer>
</body></html>
"""

_BROKEN_PAGE_HTML = "<html><body><p>page broke</p></body></html>"
_STUB_PAGE_HTML = "<html><body><div id='article'>too short</div></body></html>"


def test_extract_statement_text_pulls_article_body() -> None:
    text = _extract_statement_text(_REAL_FED_PAGE_HTML)
    assert text is not None
    assert "Recent indicators" in text
    assert "federal funds rate" in text
    # Nav / footer noise should be excluded
    assert "nav stuff" not in text
    assert "boilerplate" not in text


def test_extract_statement_text_returns_none_without_article_div() -> None:
    assert _extract_statement_text(_BROKEN_PAGE_HTML) is None


def test_extract_statement_text_rejects_stub_too_short() -> None:
    """Stub pages with #article but <200 chars text return None — they're not
    real statements (probably error pages serving the template shell)."""
    assert _extract_statement_text(_STUB_PAGE_HTML) is None


def test_item_to_raw_event_attaches_body_when_provided() -> None:
    xml = """
    <item>
      <title>Federal Reserve issues FOMC statement</title>
      <link>https://example.com/x</link>
      <description>...</description>
      <pubDate>Wed, 29 Apr 2026 18:00:00 GMT</pubDate>
    </item>
    """
    item = ET.fromstring(xml)
    event = _item_to_raw_event(item, body="Full statement text here...")
    assert event is not None
    assert event.payload["body"] == "Full statement text here..."


def test_item_to_raw_event_omits_body_when_none() -> None:
    """No body fetched → payload doesn't include 'body' key at all."""
    xml = """
    <item>
      <title>Federal Reserve issues FOMC statement</title>
      <link>https://example.com/x</link>
      <description>...</description>
      <pubDate>Wed, 29 Apr 2026 18:00:00 GMT</pubDate>
    </item>
    """
    event = _item_to_raw_event(ET.fromstring(xml), body=None)
    assert event is not None
    assert "body" not in event.payload


async def test_fetch_new_attaches_body_from_mocked_fetcher() -> None:
    """End-to-end: RSS feed parsed + body fetcher mocked, body lands in payload."""
    with (
        patch("app.adapters.fomc._fetch_feed_xml", new=AsyncMock(return_value=_SAMPLE_FEED)),
        patch(
            "app.adapters.fomc._fetch_statement_body",
            new=AsyncMock(return_value="The Committee decided to maintain rates..."),
        ),
    ):
        events = await fetch_new()
    assert len(events) == 1
    assert "maintain rates" in events[0].payload["body"]


async def test_fetch_new_emits_event_even_when_body_fetch_fails() -> None:
    """Body fetch returns None (404, timeout, parse error) → event still emits, no body key."""
    with (
        patch("app.adapters.fomc._fetch_feed_xml", new=AsyncMock(return_value=_SAMPLE_FEED)),
        patch("app.adapters.fomc._fetch_statement_body", new=AsyncMock(return_value=None)),
    ):
        events = await fetch_new()
    assert len(events) == 1
    assert "body" not in events[0].payload
