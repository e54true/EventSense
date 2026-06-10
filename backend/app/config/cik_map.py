"""Static map of ticker symbol -> SEC Central Index Key (CIK).

SEC EDGAR identifies filers by CIK, not ticker, so we need to translate before
hitting the API. CIKs are stable (they don't change with mergers / ticker
changes), so a hand-maintained map is fine for our small watchlist.

Full mapping JSON: https://www.sec.gov/files/company_tickers.json
(We could auto-fetch and cache, but for ~10 tickers a static map is simpler.)

ETFs like SPY / QQQ are excluded — they file N-CSR / N-Q rather than 8-K, so
including them here would just yield zero results from the 8-K filter.
"""

from datetime import date

# CIKs verified from https://www.sec.gov/cgi-bin/browse-edgar
TICKER_TO_CIK: dict[str, str] = {
    "AAPL": "0000320193",  # Apple Inc
    "MSFT": "0000789019",  # Microsoft Corp
    "GOOGL": "0001652044",  # Alphabet Inc Class A
    "AMZN": "0001018724",  # Amazon.com Inc
    "META": "0001326801",  # Meta Platforms Inc
    "NVDA": "0001045810",  # NVIDIA Corp
    "TSLA": "0001318605",  # Tesla Inc
    "AVGO": "0001730168",  # Broadcom Inc
    "BRK-B": "0001067983",  # Berkshire Hathaway Inc Class B
    "LLY": "0000059478",  # Eli Lilly and Co
}
"""SEC requires CIK as a 10-digit zero-padded string in URLs."""

# Tickers added to the watchlist after the system went live, with the date
# they joined. Fetchers skip events published BEFORE this date for these
# tickers — a late addition starts tracking forward from its join date
# instead of backfilling weeks of history that has no price snapshots (and
# would burn LLM analysis on outcomes that can never validate).
# Tickers absent from this map use each adapter's normal lookback window.
TICKER_INGEST_SINCE: dict[str, date] = {
    "AVGO": date(2026, 6, 11),
    "BRK-B": date(2026, 6, 11),
    "LLY": date(2026, 6, 11),
}
