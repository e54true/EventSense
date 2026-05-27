"""SEC EDGAR adapter — corporate 8-K filings.

API docs: https://www.sec.gov/edgar/sec-api-documentation
Fair-access guidelines: https://www.sec.gov/os/accessing-edgar-data
  - Max 10 req/sec per IP
  - Mandatory custom User-Agent identifying the caller

We fetch each watchlist company's submission feed, filter to form="8-K", and
emit one RawEvent per recent 8-K filing. Submissions older than LOOKBACK_DAYS
are ignored to avoid backfilling years of history on every poll.

Why 8-K matters: it's the "anything material" SEC filing — earnings results,
exec changes, M&A, bankruptcy, large contracts. High signal for price impact.
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config.cik_map import TICKER_TO_CIK
from app.config.settings import get_settings
from app.db.models import EventSource
from app.schemas.raw_event import RawEvent

logger = structlog.get_logger(__name__)

SEC_BASE = "https://data.sec.gov"
LOOKBACK_DAYS = 14  # only emit filings from the last 2 weeks

# Sleep between per-ticker requests so we stay well below 10 req/sec.
# 0.15s = ~6 req/sec, safely under the limit even with TCP overhead jitter.
_RATE_LIMIT_SLEEP = 0.15


def _user_agent_or_raise() -> str:
    ua = get_settings().sec_user_agent
    if not ua or "@" not in ua:
        raise RuntimeError(
            "SEC_USER_AGENT must be set to a string containing an email "
            "(SEC requires identification). Example: 'EventSense me@example.com'"
        )
    return ua


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_submissions(client: httpx.AsyncClient, cik: str) -> dict[str, Any]:
    """GET /submissions/CIK{cik}.json for one company."""
    response = await client.get(f"{SEC_BASE}/submissions/CIK{cik}.json")
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


def _parse_recent_8ks(
    submissions: dict[str, Any], cik: str, ticker: str, cutoff: date
) -> list[RawEvent]:
    """Walk the column-oriented `filings.recent` block and emit 8-K RawEvents.

    SEC returns filings as parallel arrays:
      accessionNumber: [...]
      filingDate: [...]
      form: [...]
      primaryDocument: [...]
      items: [...]
    We zip them together and filter to form=='8-K' newer than the cutoff.
    """
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accession_nums = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])
    items_list = recent.get("items", [])

    events: list[RawEvent] = []
    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        filing_date_str = filing_dates[i]
        filing_date = date.fromisoformat(filing_date_str)
        if filing_date < cutoff:
            continue

        accession = accession_nums[i]
        primary_doc = primary_docs[i] if i < len(primary_docs) else ""
        items = items_list[i] if i < len(items_list) else ""

        # Build the doc URL — SEC strips dashes from the accession when constructing paths
        accession_no_dashes = accession.replace("-", "")
        doc_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession_no_dashes}/{primary_doc}"
        )

        events.append(
            RawEvent(
                source=EventSource.SEC_EDGAR,
                event_type="8K_FILING",
                external_id=accession,
                title=f"{ticker} 8-K filed {filing_date_str} (items: {items or 'n/a'})",
                payload={
                    "cik": cik,
                    "ticker": ticker,
                    "accession_number": accession,
                    "filing_date": filing_date_str,
                    "item_codes": items,
                    "primary_doc_url": doc_url,
                    "company_name": submissions.get("name", ""),
                },
                affected_tickers=[ticker],
                published_at=datetime.combine(filing_date, datetime.min.time()).replace(tzinfo=UTC),
            )
        )
    return events


async def fetch_new() -> list[RawEvent]:
    """Poll all watchlist tickers and return recent 8-Ks as RawEvents."""
    user_agent = _user_agent_or_raise()
    cutoff = (datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)).date()

    log = logger.bind(source="SEC_EDGAR", tickers=len(TICKER_TO_CIK))
    log.info("sec_edgar.fetch.started")

    all_events: list[RawEvent] = []
    headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}

    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        for ticker, cik in TICKER_TO_CIK.items():
            try:
                submissions = await _fetch_submissions(client, cik)
            except httpx.HTTPStatusError as exc:
                # Don't let one bad ticker (delisted, CIK typo) sink the whole run.
                log.warning(
                    "sec_edgar.fetch.ticker_failed",
                    ticker=ticker,
                    cik=cik,
                    status=exc.response.status_code,
                )
                continue
            ticker_events = _parse_recent_8ks(submissions, cik, ticker, cutoff)
            all_events.extend(ticker_events)
            await asyncio.sleep(_RATE_LIMIT_SLEEP)

    log.info("sec_edgar.fetch.completed", parsed=len(all_events))
    return all_events
