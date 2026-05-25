"""Unit tests for FOMC adapter — RSS parsing + title filtering."""

from unittest.mock import AsyncMock, patch
from xml.etree import ElementTree as ET  # test-only: building fake feed input

from app.adapters.fomc import _is_fomc_statement, _item_to_raw_event, fetch_new
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
    with patch("app.adapters.fomc._fetch_feed_xml", new=AsyncMock(return_value=_SAMPLE_FEED)):
        events = await fetch_new()

    assert len(events) == 1
    assert events[0].source == EventSource.FOMC
    assert "FOMC" in events[0].title
