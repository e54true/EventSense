"""Downloads SEC 8-K filing bodies into the event_documents table.

For each 8-K event we:
  1. Fetch the primary doc URL already in payload (the 8-K cover form text)
  2. List the filing's index.json to enumerate sibling files
  3. Find EX-99.x exhibits (the press releases, for item 2.02 earnings 8-Ks)
  4. Download + strip each, persist with the right DocumentKind

Failure modes are local — one bad URL doesn't abort the run. Per-document
broad except, on-conflict-do-nothing dedup against uq_event_documents_event_kind.

This service stays pure of DB ownership semantics — the caller (Celery task)
manages the AsyncSession + commits, same pattern as event_writer.persist_events.
"""

import re
import uuid
from datetime import UTC, datetime

import httpx
import structlog
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.models import DocumentKind, Event, EventDocument, EventSource

logger = structlog.get_logger(__name__)

_REQUEST_TIMEOUT_SEC = 20.0
# SEC's fair-access guidelines: 10 req/sec max, mandatory custom User-Agent.
# Same User-Agent format the SEC adapter uses (must contain an email).
# Cap content per document so a single bloated filing doesn't blow the prompt budget.
_MAX_DOC_CHARS = 80_000  # ~20K tokens — comfortable for gpt-4o-mini

# Files inside a SEC filing whose names match this regex are treated as
# exhibit 99.x candidates — i.e. potential press releases / earnings materials.
# Matches: ex991.htm, ex99-1.htm, ex-99.1.htm, exhibit991.htm, etc.
_EX99_PATTERN = re.compile(r"^ex(hibit)?[-_.]?99", re.IGNORECASE)


def _sec_headers() -> dict[str, str]:
    ua = get_settings().sec_user_agent
    if not ua or "@" not in ua:
        raise RuntimeError(
            "SEC_USER_AGENT must contain an email for the SEC fair-access policy"
        )
    return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}


def _strip_html(html: str) -> str | None:
    """BeautifulSoup-strip the document body. Returns None if too short to be meaningful."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        # Drop noise tags that bloat token cost without adding signal.
        for tag in soup(["script", "style", "noscript", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Collapse multi-blank-line runs.
        text = re.sub(r"\n{3,}", "\n\n", text)
        if len(text) < 200:
            return None
        return text[:_MAX_DOC_CHARS]
    except Exception as exc:
        logger.warning("doc_fetcher.strip_failed", error=str(exc))
        return None


async def _fetch_and_strip(client: httpx.AsyncClient, url: str) -> str | None:
    """GET url + strip to text. Broad-except — failures return None."""
    try:
        response = await client.get(url)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("doc_fetcher.fetch_failed", url=url, error=str(exc))
        return None
    return _strip_html(response.text)


async def _list_exhibit_files(client: httpx.AsyncClient, index_url: str) -> list[str]:
    """Hit the filing's index.json, return filenames matching the EX-99.x pattern."""
    try:
        response = await client.get(index_url)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("doc_fetcher.index_fetch_failed", url=index_url, error=str(exc))
        return []
    items = data.get("directory", {}).get("item", [])
    return [
        item["name"]
        for item in items
        if "name" in item and _EX99_PATTERN.match(item["name"])
    ]


async def _persist_document(
    db: AsyncSession,
    event_id: uuid.UUID,
    doc_kind: DocumentKind,
    content: str,
    raw_url: str,
) -> bool:
    """Insert one EventDocument. Returns True if inserted, False if it already existed."""
    # Pre-check: skip if (event_id, doc_kind) already present. The unique constraint
    # is still the authoritative dedup but the SELECT avoids burning a transaction
    # on the common "second adapter run for an already-fetched event" path.
    existing = await db.scalar(
        select(EventDocument.id).where(
            EventDocument.event_id == event_id,
            EventDocument.doc_kind == doc_kind,
        )
    )
    if existing is not None:
        return False

    doc = EventDocument(
        event_id=event_id,
        doc_kind=doc_kind,
        content_text=content,
        raw_url=raw_url[:500],
        byte_size=len(content.encode("utf-8")),
        fetched_at=datetime.now(UTC),
    )
    db.add(doc)
    try:
        await db.flush()
        return True
    except IntegrityError:
        await db.rollback()
        return False


async def fetch_documents_for_event(db: AsyncSession, event: Event) -> int:
    """Fetch and persist all available documents for one 8-K event.

    Returns the count of new event_documents rows inserted.
    """
    if event.source != EventSource.SEC_EDGAR or event.event_type != "8K_FILING":
        return 0

    cik = event.payload.get("cik")
    accession = event.payload.get("accession_number")
    primary_url = event.payload.get("primary_doc_url")
    if not (cik and accession and primary_url):
        logger.warning(
            "doc_fetcher.missing_payload_fields",
            event_id=str(event.id),
            has_cik=bool(cik),
            has_accession=bool(accession),
            has_primary_url=bool(primary_url),
        )
        return 0

    accession_no_dashes = str(accession).replace("-", "")
    cik_int = str(int(cik))  # drop leading zeros to match SEC archives URL convention
    archives_base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_no_dashes}"
    index_url = f"{archives_base}/index.json"

    log = logger.bind(event_id=str(event.id), accession=accession)
    log.info("doc_fetcher.started")
    inserted = 0

    async with httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT_SEC,
        headers=_sec_headers(),
        follow_redirects=True,
    ) as client:
        # 1. Primary doc — always treat as FILING_COVER.
        cover_text = await _fetch_and_strip(client, primary_url)
        if cover_text and await _persist_document(
            db, event.id, DocumentKind.FILING_COVER, cover_text, primary_url
        ):
            inserted += 1

        # 2. EX-99.x exhibits → first match = PRESS_RELEASE, second = EXHIBIT.
        # UNIQUE(event_id, doc_kind) caps us at one of each. Filings with 3+
        # exhibits are rare in 8-Ks; the extras log-warn and skip.
        exhibits = await _list_exhibit_files(client, index_url)
        slot_order = [DocumentKind.PRESS_RELEASE, DocumentKind.EXHIBIT]
        for i, filename in enumerate(exhibits):
            if i >= len(slot_order):
                log.info("doc_fetcher.extra_exhibit_skipped", filename=filename)
                break
            exhibit_url = f"{archives_base}/{filename}"
            text = await _fetch_and_strip(client, exhibit_url)
            if text is None:
                continue
            if await _persist_document(db, event.id, slot_order[i], text, exhibit_url):
                inserted += 1

    await db.commit()
    log.info("doc_fetcher.completed", inserted=inserted, exhibit_count=len(exhibits))
    return inserted
