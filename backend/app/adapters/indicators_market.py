"""Market-valuation indicator adapter — scrapes multpl.com for S&P 500 metrics.

multpl.com is an aggregator that publishes daily-updated valuation stats with a
remarkably stable HTML structure: every metric page has a `<div id="current">`
containing the latest value as plain text.

Indicators we scrape:
- SP500_PE       trailing P/E ratio       (from /s-p-500-pe-ratio)
- SP500_TTM_EPS  trailing 12-month EPS    (from /s-p-500-earnings)

Forward EPS is intentionally NOT scraped — multpl doesn't publish a free
structured-data page for it, and yfinance's ^GSPC/SPY don't expose forwardEps
either. Treating that as a known gap (revisit if we add FactSet or similar).

Every fetch is wrapped in broad except so a multpl HTML change degrades to
"indicator missing" rather than crashing the worker.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import structlog
from bs4 import BeautifulSoup

from app.schemas.indicator import IndicatorObservation

logger = structlog.get_logger(__name__)

_REQUEST_TIMEOUT_SEC = 15.0
_USER_AGENT = "Mozilla/5.0 (compatible; EventSense/0.1)"


@dataclass(frozen=True, slots=True)
class MultplSpec:
    url: str
    indicator_key: str


MULTPL_SPECS: list[MultplSpec] = [
    MultplSpec("https://www.multpl.com/s-p-500-pe-ratio", "SP500_PE"),
    MultplSpec("https://www.multpl.com/s-p-500-earnings", "SP500_TTM_EPS"),
]


def _parse_current_value(html: str) -> float | None:
    """Extract the numeric value from multpl's `<div id="current">` block.

    The block looks like:
        <div id="current">
            <b>Current<span class="currentTitle">S&P 500 PE Ratio</span>:</b>
            31.83
            <span class="neg">-0.86 (-2.64%)</span>
            ...
        </div>

    Strategy: take the text of the div, drop the title/change/timestamp lines,
    keep the first standalone numeric token.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        block = soup.find("div", id="current")
        if block is None:
            return None
        # Remove the inner <span> (title, % change, timestamp) so we're left with
        # the bare value as plain text.
        for span in block.find_all("span"):
            span.decompose()
        # Also strip the leading "<b>Current...:</b>" so only the value remains.
        b_tag = block.find("b")
        if b_tag is not None:
            b_tag.decompose()
        text = block.get_text(separator=" ", strip=True)
        # First token. Strip trailing punctuation/%/etc.
        for token in text.split():
            cleaned = token.rstrip("%").rstrip(",").strip()
            try:
                return float(cleaned)
            except ValueError:
                continue
        return None
    except Exception as exc:
        logger.warning("multpl.parse.failed", error=str(exc))
        return None


async def _fetch_html(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT_SEC,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except Exception as exc:
        logger.warning("multpl.fetch.failed", url=url, error=str(exc))
        return None


async def fetch_new() -> list[IndicatorObservation]:
    """Scrape every multpl spec; missing values are skipped (degrades gracefully)."""
    log = logger.bind(source="MULTPL", specs=len(MULTPL_SPECS))
    log.info("indicators_market.fetch.started")

    observations: list[IndicatorObservation] = []
    now = datetime.now(UTC)

    for spec in MULTPL_SPECS:
        html = await _fetch_html(spec.url)
        if html is None:
            continue
        value = _parse_current_value(html)
        if value is None:
            log.warning("multpl.value.missing", indicator_key=spec.indicator_key, url=spec.url)
            continue
        observations.append(
            IndicatorObservation(
                indicator_key=spec.indicator_key,
                # multpl publishes daily; observed_at is the fetch timestamp truncated
                # to the day boundary so the (key, observed_at) dedup constraint
                # short-circuits intra-day re-polls.
                observed_at=now.replace(hour=0, minute=0, second=0, microsecond=0),
                value=value,
                source="MULTPL",
                payload={"url": spec.url},
            )
        )

    log.info("indicators_market.fetch.completed", parsed=len(observations))
    return observations
