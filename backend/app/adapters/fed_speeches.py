"""Fed speeches + testimony adapter — the Fed's unscheduled market-movers.

Source: the Federal Reserve Board's RSS feeds for speeches and testimony.
  https://www.federalreserve.gov/feeds/speeches.xml
  https://www.federalreserve.gov/feeds/testimony.xml

These cover Board officials (Chair / Vice Chair / Governors) — the highest-
impact Fed speakers. Regional Fed presidents publish on their own sites and
are out of scope (a future adapter).

We parse each RSS, and for every item download the speech/testimony HTML page
to extract (a) the body text, (b) the speaker + role from the page's
`p.speaker` element (more reliable than the feed title, which carries only a
last name), and (c) the venue from `p.location`. Body/speaker fetch failures
degrade gracefully — the RawEvent still emits, just without those payload keys.

Why this is safe for the M9.6 accuracy discipline: a Fed speech is an official
publication with an authoritative `pubDate`, which we map straight to
`published_at`. The validator therefore anchors the +24h/+7d window on the
moment the market actually learned the information — the same release-date
discipline FOMC statements rely on, unlike third-party news headlines whose
"when did the market see this" timestamp is untrustworthy.

Mirrors app/adapters/fomc.py's structure (defusedxml + httpx + tenacity +
two-phase body fetch); kept a separate module so the two Fed sources stay
independently testable.
"""

from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
import structlog
from bs4 import BeautifulSoup

# defusedxml hardens stdlib xml parsing against XXE / billion-laughs attacks.
from defusedxml import ElementTree as ET
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config.settings import get_settings
from app.db.models import EventSource
from app.schemas.raw_event import RawEvent

logger = structlog.get_logger(__name__)

SPEECHES_FEED_URL = "https://www.federalreserve.gov/feeds/speeches.xml"
TESTIMONY_FEED_URL = "https://www.federalreserve.gov/feeds/testimony.xml"
_USER_AGENT = "EventSense/0.1 dev@example.com"
_BODY_FETCH_TIMEOUT_SEC = 15.0
# Cap the inlined body to keep prompt tokens bounded. Speeches run long
# (observed ~27 KB); 10 KB keeps the key argument without blowing the budget.
_MAX_BODY_CHARS = 10_000
# Pages shorter than this are stub/error shells, not a real speech.
_MIN_BODY_CHARS = 200

# event_type strings. Not in analyzer._COMPANY_EVENT_TYPES, so both auto-route
# MARKET-only (SPY/QQQ). FED_TESTIMONY is in router._HIGH_STAKES_EVENT_TYPES.
EVENT_TYPE_SPEECH = "FED_SPEECH"
EVENT_TYPE_TESTIMONY = "FED_TESTIMONY"


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_feed_xml(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": _USER_AGENT}) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def _parse_pub_date(text: str | None) -> datetime | None:
    """RSS pubDate is RFC 822 ('Sat, 6 Jun 2026 16:00:00 GMT'). Convert to tz-aware."""
    if not text:
        return None
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None


def _speaker_from_title(title: str) -> str | None:
    """Feed titles are 'LastName, Speech Title' — take the leading last name.

    Fallback only: the page's `p.speaker` (full name + role) is preferred.
    """
    if "," in title:
        return title.split(",", 1)[0].strip() or None
    return None


def _role_tier(page_speaker: str | None) -> str:
    """Coarse impact tier from the page speaker string ('Chair Jerome H. Powell').

    The Board feeds only carry Board officials, so this 3-way split is
    exhaustive. Check 'vice chair' before 'chair' (substring). Unknown/missing
    speaker → GOVERNOR (the lowest tier; never over-escalates).
    """
    if not page_speaker:
        return "GOVERNOR"
    low = page_speaker.lower()
    if "vice chair" in low:
        return "VICE_CHAIR"
    if "chair" in low:
        return "CHAIR"
    return "GOVERNOR"


def _event_type_for(category: str, default: str) -> str:
    """Map the feed <category> ('Speech' / 'Testimony') to our event_type."""
    low = category.lower()
    if "testimony" in low:
        return EVENT_TYPE_TESTIMONY
    if "speech" in low:
        return EVENT_TYPE_SPEECH
    return default


def _passes_speaker_scope(role_tier: str, scope: str) -> bool:
    """Whether a speaker of `role_tier` is in the configured ingest scope.

    'all' (default) → everyone; 'principals' → Chair + Vice Chair;
    'chair' → Chair only. Unknown scope values fail open (never silently drop).
    """
    if scope == "principals":
        return role_tier in ("CHAIR", "VICE_CHAIR")
    if scope == "chair":
        return role_tier == "CHAIR"
    return True


def _parse_speech_page(html: str) -> tuple[str | None, str | None, str | None]:
    """Extract (body, speaker, location) from a Fed speech/testimony page.

    Body lives in the `#article` div (same template as press releases). The
    speaker ('Governor Michael S. Barr') and venue come from `p.speaker` /
    `p.location`. Any missing piece returns None for that slot — the event
    still emits. Pure function (no network) so it's unit-testable.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        logger.warning("fed_speeches.page.parse_failed", error=str(exc))
        return None, None, None

    speaker_node = soup.select_one("p.speaker")
    speaker = speaker_node.get_text(strip=True) if speaker_node else None
    location_node = soup.select_one("p.location")
    location = location_node.get_text(strip=True) if location_node else None

    body: str | None = None
    article = soup.select_one("#article")
    if article is not None:
        text = article.get_text(separator="\n", strip=True)
        if len(text) >= _MIN_BODY_CHARS:  # stub/error-page guard (mirror fomc.py)
            body = text[:_MAX_BODY_CHARS]

    return body, speaker, location


async def _fetch_page(
    client: httpx.AsyncClient, url: str
) -> tuple[str | None, str | None, str | None]:
    """Fetch a speech page and parse it. Broad-except → (None, None, None)."""
    try:
        response = await client.get(url)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("fed_speeches.page.fetch_failed", url=url, error=str(exc))
        return None, None, None
    return _parse_speech_page(response.text)


def _item_to_raw_event(
    item: Any,
    *,
    default_event_type: str,
    body: str | None = None,
    page_speaker: str | None = None,
    location: str | None = None,
) -> RawEvent | None:
    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or "").strip()
    description = (item.findtext("description") or "").strip()
    category = (item.findtext("category") or "").strip()
    pub_date_text = item.findtext("pubDate")

    if not title or not link:
        return None
    published_at = _parse_pub_date(pub_date_text)
    if published_at is None:
        return None

    payload: dict[str, Any] = {
        "title": title,
        "link": link,
        "description": description,
        "pub_date": pub_date_text,
        "category": category,
        # Page-derived full name + role preferred; title last-name as fallback.
        "speaker": page_speaker or _speaker_from_title(title),
        "role_tier": _role_tier(page_speaker),
    }
    if location:
        payload["location"] = location
    if body:
        payload["body"] = body

    return RawEvent(
        source=EventSource.FOMC,
        event_type=_event_type_for(category, default_event_type),
        external_id=link,
        title=title[:500],
        payload=payload,
        affected_tickers=[],  # Fed speech moves the whole market; mapping in Analyzer
        published_at=published_at,
    )


async def _fetch_feed(
    client: httpx.AsyncClient, url: str, default_event_type: str, scope: str
) -> tuple[list[RawEvent], int, int]:
    """Parse one feed: fetch each item's page, build + scope-filter events.

    We fetch the page BEFORE the scope check rather than pre-filtering: the
    role tier is only reliable from the page's `p.speaker` (the feed title is
    just a last name), and the default scope='all' fetches every body anyway,
    so there's no waste in the common case. Narrow scopes pay a bounded
    handful of discarded GETs per run — cheaper than a brittle name→role table
    that breaks every time the Board roster changes.
    """
    xml_bytes = await _fetch_feed_xml(url)
    root = ET.fromstring(xml_bytes)
    items = root.findall("./channel/item")

    events: list[RawEvent] = []
    bodies_fetched = 0
    for item in items:
        link = (item.findtext("link") or "").strip()
        body, page_speaker, location = (
            await _fetch_page(client, link) if link else (None, None, None)
        )
        if body:
            bodies_fetched += 1
        event = _item_to_raw_event(
            item,
            default_event_type=default_event_type,
            body=body,
            page_speaker=page_speaker,
            location=location,
        )
        if event is None:
            continue
        if not _passes_speaker_scope(str(event.payload["role_tier"]), scope):
            continue
        events.append(event)
    return events, bodies_fetched, len(items)


async def fetch_new() -> list[RawEvent]:
    log = logger.bind(source="FED_SPEECHES")
    log.info("fed_speeches.fetch.started")

    scope = get_settings().fed_speaker_scope
    events: list[RawEvent] = []
    bodies_fetched = 0
    total_items = 0

    headers = {"User-Agent": _USER_AGENT}
    async with httpx.AsyncClient(
        timeout=_BODY_FETCH_TIMEOUT_SEC, headers=headers, follow_redirects=True
    ) as client:
        for url, default_event_type in (
            (SPEECHES_FEED_URL, EVENT_TYPE_SPEECH),
            (TESTIMONY_FEED_URL, EVENT_TYPE_TESTIMONY),
        ):
            evs, bodies, n = await _fetch_feed(client, url, default_event_type, scope)
            events.extend(evs)
            bodies_fetched += bodies
            total_items += n

    log.info(
        "fed_speeches.fetch.completed",
        parsed=len(events),
        bodies_fetched=bodies_fetched,
        total_items=total_items,
        scope=scope,
    )
    return events
