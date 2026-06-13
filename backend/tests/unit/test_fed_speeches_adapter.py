"""Unit tests for the Fed speeches/testimony adapter.

Mirrors test_fomc_adapter.py: in-memory XML/HTML fixtures + AsyncMock patches,
no network. Real feed/page structure was confirmed live before writing these
(speeches.xml / testimony.xml: title 'LastName, Title', link==guid,
category Speech|Testimony; speech pages carry the body in #article and the
speaker/role in p.speaker).
"""

from unittest.mock import AsyncMock, patch
from xml.etree import ElementTree as ET  # test-only: building fake feed input

import pytest

from app.adapters.fed_speeches import (
    EVENT_TYPE_SPEECH,
    EVENT_TYPE_TESTIMONY,
    _event_type_for,
    _item_to_raw_event,
    _parse_speech_page,
    _passes_speaker_scope,
    _role_tier,
    _speaker_from_title,
    fetch_new,
)
from app.db.models import EventSource


@pytest.fixture(autouse=True)
def _scope_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default tests to scope=all; individual tests override + cache_clear."""
    monkeypatch.setenv("FED_SPEAKER_SCOPE", "all")
    from app.config.settings import get_settings

    get_settings.cache_clear()


# --- speaker / role parsing ---


def test_speaker_from_title_takes_leading_lastname() -> None:
    assert _speaker_from_title("Powell, The Economic Outlook") == "Powell"
    assert _speaker_from_title("Barr, Deregulating in a Financial Boom") == "Barr"


def test_speaker_from_title_none_without_comma() -> None:
    assert _speaker_from_title("Some title without a comma") is None


def test_role_tier_classifies_page_speaker() -> None:
    assert _role_tier("Chair Jerome H. Powell") == "CHAIR"
    assert _role_tier("Vice Chair Philip N. Jefferson") == "VICE_CHAIR"
    assert _role_tier("Governor Michael S. Barr") == "GOVERNOR"
    # Missing speaker (body fetch failed) → lowest tier, never over-escalates.
    assert _role_tier(None) == "GOVERNOR"
    # "Vice Chair" must win over the "Chair" substring.
    assert _role_tier("Vice Chair for Supervision Michelle W. Bowman") == "VICE_CHAIR"


def test_event_type_from_category() -> None:
    assert _event_type_for("Speech", EVENT_TYPE_SPEECH) == EVENT_TYPE_SPEECH
    assert _event_type_for("Testimony", EVENT_TYPE_TESTIMONY) == EVENT_TYPE_TESTIMONY
    # Unknown/empty category → per-feed default.
    assert _event_type_for("", EVENT_TYPE_TESTIMONY) == EVENT_TYPE_TESTIMONY


def test_passes_speaker_scope() -> None:
    assert _passes_speaker_scope("GOVERNOR", "all")
    assert _passes_speaker_scope("CHAIR", "principals")
    assert _passes_speaker_scope("VICE_CHAIR", "principals")
    assert not _passes_speaker_scope("GOVERNOR", "principals")
    assert _passes_speaker_scope("CHAIR", "chair")
    assert not _passes_speaker_scope("VICE_CHAIR", "chair")
    # Unknown scope fails open.
    assert _passes_speaker_scope("GOVERNOR", "weird")


# --- page parsing (body + speaker + location) ---


_REAL_SPEECH_PAGE = """
<html><body>
<header>nav junk</header>
<p class="speaker"><a href="/aboutthefed/bios/board/powell.htm">Chair Jerome H. Powell</a></p>
<p class="location">At the Economic Club of Washington, D.C.</p>
<div id="article">
<h3>The Economic Outlook</h3>
<p>Recent indicators suggest that economic activity has continued to expand. The labor market remains solid and inflation has eased but remains somewhat above our two percent objective over the longer run.</p>
<p>We will continue to make our decisions meeting by meeting, based on the totality of the incoming data and the evolving outlook and balance of risks.</p>
</div>
<footer>boilerplate</footer>
</body></html>
"""

_NO_ARTICLE_PAGE = "<html><body><p class='speaker'>Chair Jerome H. Powell</p></body></html>"
_STUB_ARTICLE_PAGE = "<html><body><div id='article'>too short</div></body></html>"


def test_parse_speech_page_pulls_body_speaker_location() -> None:
    body, speaker, location = _parse_speech_page(_REAL_SPEECH_PAGE)
    assert body is not None
    assert "Recent indicators" in body
    assert "meeting by meeting" in body
    assert "nav junk" not in body  # header/footer excluded
    assert "boilerplate" not in body
    assert speaker == "Chair Jerome H. Powell"
    assert location == "At the Economic Club of Washington, D.C."


def test_parse_speech_page_no_article_returns_no_body() -> None:
    body, speaker, _location = _parse_speech_page(_NO_ARTICLE_PAGE)
    assert body is None
    assert speaker == "Chair Jerome H. Powell"  # speaker still extracted


def test_parse_speech_page_rejects_stub_body() -> None:
    body, _speaker, _location = _parse_speech_page(_STUB_ARTICLE_PAGE)
    assert body is None


# --- _item_to_raw_event ---


def _item(
    title: str, link: str, category: str, pub: str = "Sat, 6 Jun 2026 16:00:00 GMT"
) -> object:
    xml = f"""
    <item>
      <title>{title}</title>
      <link>{link}</link>
      <description>{category} At Some Venue</description>
      <category>{category}</category>
      <pubDate>{pub}</pubDate>
    </item>
    """
    return ET.fromstring(xml)


def test_item_to_raw_event_speech() -> None:
    item = _item(
        "Powell, The Economic Outlook",
        "https://www.federalreserve.gov/newsevents/speech/powell20260606a.htm",
        "Speech",
    )
    event = _item_to_raw_event(
        item, default_event_type=EVENT_TYPE_SPEECH, page_speaker="Chair Jerome H. Powell"
    )
    assert event is not None
    assert event.source == EventSource.FOMC
    assert event.event_type == EVENT_TYPE_SPEECH
    assert event.external_id == event.payload["link"]
    assert event.payload["speaker"] == "Chair Jerome H. Powell"
    assert event.payload["role_tier"] == "CHAIR"
    assert event.payload["category"] == "Speech"
    assert event.affected_tickers == []
    assert event.published_at.year == 2026


def test_item_to_raw_event_testimony_uses_category() -> None:
    item = _item(
        "Bowman, Supervision and Regulation",
        "https://www.federalreserve.gov/newsevents/testimony/bowman20260604a.htm",
        "Testimony",
    )
    # Even with the speech default, the <category> drives event_type.
    event = _item_to_raw_event(
        item, default_event_type=EVENT_TYPE_SPEECH, page_speaker="Governor Michelle W. Bowman"
    )
    assert event is not None
    assert event.event_type == EVENT_TYPE_TESTIMONY
    assert event.payload["role_tier"] == "GOVERNOR"


def test_item_to_raw_event_falls_back_to_title_speaker() -> None:
    """Body fetch failed → no page_speaker → speaker is the title last name,
    role defaults to GOVERNOR."""
    item = _item("Waller, A Thoughtful Speech", "https://x.gov/waller.htm", "Speech")
    event = _item_to_raw_event(item, default_event_type=EVENT_TYPE_SPEECH, page_speaker=None)
    assert event is not None
    assert event.payload["speaker"] == "Waller"
    assert event.payload["role_tier"] == "GOVERNOR"


def test_item_to_raw_event_attaches_body_when_provided() -> None:
    item = _item("Powell, Remarks", "https://x.gov/p.htm", "Speech")
    event = _item_to_raw_event(
        item, default_event_type=EVENT_TYPE_SPEECH, body="Full speech text here..."
    )
    assert event is not None
    assert event.payload["body"] == "Full speech text here..."


def test_item_to_raw_event_omits_body_when_none() -> None:
    item = _item("Powell, Remarks", "https://x.gov/p.htm", "Speech")
    event = _item_to_raw_event(item, default_event_type=EVENT_TYPE_SPEECH, body=None)
    assert event is not None
    assert "body" not in event.payload


def test_item_to_raw_event_skips_missing_pub_date() -> None:
    xml = """
    <item>
      <title>Powell, Remarks</title>
      <link>https://x.gov/p.htm</link>
      <category>Speech</category>
    </item>
    """
    assert _item_to_raw_event(ET.fromstring(xml), default_event_type=EVENT_TYPE_SPEECH) is None


def test_item_to_raw_event_skips_missing_link() -> None:
    xml = """
    <item>
      <title>Powell, Remarks</title>
      <link></link>
      <category>Speech</category>
      <pubDate>Sat, 6 Jun 2026 16:00:00 GMT</pubDate>
    </item>
    """
    assert _item_to_raw_event(ET.fromstring(xml), default_event_type=EVENT_TYPE_SPEECH) is None


# --- fetch_new (both feeds) ---


_SPEECH_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Powell, The Economic Outlook</title>
    <link>https://www.federalreserve.gov/newsevents/speech/powell20260606a.htm</link>
    <description>Speech At the Economic Club</description>
    <category>Speech</category>
    <pubDate>Sat, 6 Jun 2026 16:00:00 GMT</pubDate>
  </item>
</channel></rss>
"""

_TESTIMONY_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Bowman, Supervision and Regulation</title>
    <link>https://www.federalreserve.gov/newsevents/testimony/bowman20260604a.htm</link>
    <description>Testimony Before the Committee</description>
    <category>Testimony</category>
    <pubDate>Wed, 3 Jun 2026 20:30:00 GMT</pubDate>
  </item>
</channel></rss>
"""


async def test_fetch_new_parses_both_feeds() -> None:
    """Both feeds parsed, page fetch mocked → one speech + one testimony event."""
    page = (None, "Chair Jerome H. Powell", "At the Economic Club")
    with (
        patch(
            "app.adapters.fed_speeches._fetch_feed_xml",
            new=AsyncMock(side_effect=[_SPEECH_FEED, _TESTIMONY_FEED]),
        ),
        patch("app.adapters.fed_speeches._fetch_page", new=AsyncMock(return_value=page)),
    ):
        events = await fetch_new()

    assert len(events) == 2
    by_type = {e.event_type for e in events}
    assert by_type == {EVENT_TYPE_SPEECH, EVENT_TYPE_TESTIMONY}
    assert all(e.source == EventSource.FOMC for e in events)


async def test_fetch_new_scope_principals_drops_governor(monkeypatch: pytest.MonkeyPatch) -> None:
    """scope=principals: a Governor speech is dropped, the Chair survives."""
    monkeypatch.setenv("FED_SPEAKER_SCOPE", "principals")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    # Speech feed item is Powell (CHAIR); testimony feed item is Bowman (GOVERNOR).
    def _page(_client: object, url: str) -> tuple[None, str, str]:
        if "powell" in url:
            return (None, "Chair Jerome H. Powell", "Venue")
        return (None, "Governor Michelle W. Bowman", "Committee")

    with (
        patch(
            "app.adapters.fed_speeches._fetch_feed_xml",
            new=AsyncMock(side_effect=[_SPEECH_FEED, _TESTIMONY_FEED]),
        ),
        patch("app.adapters.fed_speeches._fetch_page", new=AsyncMock(side_effect=_page)),
    ):
        events = await fetch_new()

    assert len(events) == 1
    assert events[0].payload["role_tier"] == "CHAIR"
    assert events[0].event_type == EVENT_TYPE_SPEECH
