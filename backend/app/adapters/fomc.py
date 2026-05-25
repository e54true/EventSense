"""FOMC adapter — Federal Reserve monetary policy statements.

Source: Federal Reserve's press release RSS feed for monetary policy.
  https://www.federalreserve.gov/feeds/press_monetary.xml

We parse the RSS, filter to items that look like FOMC statements (vs other
monetary-policy press releases like minutes/testimony), and emit one RawEvent
per statement. Rate-change extraction (e.g. "+25 bps") is left for the Analyzer
milestone — for now we just store the raw description text.

Why not use feedparser library: stdlib xml.etree handles this well-formed feed
fine, and adding a dep that isn't actively maintained isn't worth it for ~20
lines of parsing.
"""

from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
import structlog

# defusedxml hardens stdlib xml parsing against XXE / billion-laughs attacks.
# Drop-in API-compatible with xml.etree.ElementTree.
from defusedxml import ElementTree as ET
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.db.models import EventSource
from app.schemas.raw_event import RawEvent

logger = structlog.get_logger(__name__)

FOMC_FEED_URL = "https://www.federalreserve.gov/feeds/press_monetary.xml"

# RSS items we care about: titles tend to look like one of:
#   "Federal Reserve issues FOMC statement"
#   "FOMC statement"
# We match permissively so we don't miss formatting changes.
_FOMC_TITLE_MARKERS = ("fomc statement", "fomc issues")


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_feed_xml() -> bytes:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(FOMC_FEED_URL)
        response.raise_for_status()
        return response.content


def _is_fomc_statement(title: str) -> bool:
    lower = title.lower()
    return any(marker in lower for marker in _FOMC_TITLE_MARKERS)


def _parse_pub_date(text: str | None) -> datetime | None:
    """RSS pubDate is RFC 822 ('Wed, 18 Mar 2026 18:00:00 GMT'). Convert to tz-aware."""
    if not text:
        return None
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None


def _item_to_raw_event(item: Any) -> RawEvent | None:
    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or "").strip()
    description = (item.findtext("description") or "").strip()
    pub_date_text = item.findtext("pubDate")

    if not title or not _is_fomc_statement(title):
        return None

    published_at = _parse_pub_date(pub_date_text)
    if published_at is None:
        return None

    # Use the link as external_id — each press release has a unique URL.
    if not link:
        return None

    payload: dict[str, Any] = {
        "title": title,
        "link": link,
        "description": description,
        "pub_date": pub_date_text,
    }

    return RawEvent(
        source=EventSource.FOMC,
        event_type="FOMC_STATEMENT",
        external_id=link,
        title=title[:500],
        payload=payload,
        affected_tickers=[],  # FOMC affects the whole market; per-ticker mapping in Analyzer
        published_at=published_at,
    )


async def fetch_new() -> list[RawEvent]:
    log = logger.bind(source="FOMC")
    log.info("fomc.fetch.started")

    xml_bytes = await _fetch_feed_xml()
    root = ET.fromstring(xml_bytes)

    # RSS structure: <rss><channel><item>...</item><item>...</item></channel></rss>
    items = root.findall("./channel/item")
    events = [e for item in items if (e := _item_to_raw_event(item))]

    log.info("fomc.fetch.completed", parsed=len(events), total_items=len(items))
    return events
