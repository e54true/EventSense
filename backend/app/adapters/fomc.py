"""FOMC adapter — Federal Reserve monetary policy statements.

Source: Federal Reserve's press release RSS feed for monetary policy.
  https://www.federalreserve.gov/feeds/press_monetary.xml

We parse the RSS, filter to items that look like FOMC statements (vs other
monetary-policy press releases like minutes/testimony), and emit one RawEvent
per statement.

Phase C: After the RSS parse, we also download each statement's HTML body
from its `link` URL and BeautifulSoup-extract the actual press release text
(`#article` div). That text — ~2-3 KB of monetary-policy language — lands
in payload.body so the v2 analyzer can read what the Fed actually said
instead of just "Federal Reserve issues FOMC statement". Body fetch failures
degrade gracefully — the RawEvent still emits, just without payload.body.

Why not use feedparser library: stdlib xml.etree handles this well-formed feed
fine, and adding a dep that isn't actively maintained isn't worth it for ~20
lines of parsing.
"""

from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
import structlog
from bs4 import BeautifulSoup

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
_USER_AGENT = "EventSense/0.1 dev@example.com"
_BODY_FETCH_TIMEOUT_SEC = 15.0
# Cap the inlined statement body to keep prompt tokens bounded. Real FOMC
# statements run ~2-3 KB; 10 KB is generous headroom for unusual long ones.
_MAX_BODY_CHARS = 10_000

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


def _item_to_raw_event(item: Any, body: str | None = None) -> RawEvent | None:
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
    if body:
        payload["body"] = body

    return RawEvent(
        source=EventSource.FOMC,
        event_type="FOMC_STATEMENT",
        external_id=link,
        title=title[:500],
        payload=payload,
        affected_tickers=[],  # FOMC affects the whole market; per-ticker mapping in Analyzer
        published_at=published_at,
    )


def _extract_statement_text(html: str) -> str | None:
    """Pull the FOMC press-release body out of a Fed press-release page.

    The Fed's templates put the release inside a `#article` div. If that
    selector ever changes we fall back to None and the RawEvent still emits
    without body.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        article = soup.select_one("#article")
        if article is None:
            return None
        text = article.get_text(separator="\n", strip=True)
        if len(text) < 200:
            # Too short to be a real statement — probably a stub page.
            return None
        return text[:_MAX_BODY_CHARS]
    except Exception as exc:
        logger.warning("fomc.body.parse_failed", error=str(exc))
        return None


async def _fetch_statement_body(client: httpx.AsyncClient, url: str) -> str | None:
    """Fetch a Fed press release HTML page and extract its body text.

    Broad-except: any failure (404, timeout, parse error) yields None.
    """
    try:
        response = await client.get(url)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("fomc.body.fetch_failed", url=url, error=str(exc))
        return None
    return _extract_statement_text(response.text)


async def fetch_new() -> list[RawEvent]:
    log = logger.bind(source="FOMC")
    log.info("fomc.fetch.started")

    xml_bytes = await _fetch_feed_xml()
    root = ET.fromstring(xml_bytes)

    # RSS structure: <rss><channel><item>...</item><item>...</item></channel></rss>
    items = root.findall("./channel/item")

    events: list[RawEvent] = []
    bodies_fetched = 0
    headers = {"User-Agent": _USER_AGENT}
    async with httpx.AsyncClient(
        timeout=_BODY_FETCH_TIMEOUT_SEC, headers=headers, follow_redirects=True
    ) as client:
        for item in items:
            # Quick pre-filter: skip non-FOMC-statement items without an HTTP call.
            title = (item.findtext("title") or "").strip()
            if not _is_fomc_statement(title):
                continue
            link = (item.findtext("link") or "").strip()
            body = await _fetch_statement_body(client, link) if link else None
            if body:
                bodies_fetched += 1
            event = _item_to_raw_event(item, body=body)
            if event is not None:
                events.append(event)

    log.info(
        "fomc.fetch.completed",
        parsed=len(events),
        bodies_fetched=bodies_fetched,
        total_items=len(items),
    )
    return events
