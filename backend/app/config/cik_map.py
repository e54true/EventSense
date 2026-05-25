"""Static map of ticker symbol -> SEC Central Index Key (CIK).

SEC EDGAR identifies filers by CIK, not ticker, so we need to translate before
hitting the API. CIKs are stable (they don't change with mergers / ticker
changes), so a hand-maintained map is fine for our small watchlist.

Full mapping JSON: https://www.sec.gov/files/company_tickers.json
(We could auto-fetch and cache, but for ~10 tickers a static map is simpler.)

ETFs like SPY / QQQ are excluded — they file N-CSR / N-Q rather than 8-K, so
including them here would just yield zero results from the 8-K filter.
"""

# CIKs verified from https://www.sec.gov/cgi-bin/browse-edgar
TICKER_TO_CIK: dict[str, str] = {
    "AAPL": "0000320193",   # Apple Inc
    "MSFT": "0000789019",   # Microsoft Corp
    "GOOGL": "0001652044",  # Alphabet Inc Class A
    "AMZN": "0001018724",   # Amazon.com Inc
    "META": "0001326801",   # Meta Platforms Inc
    "NVDA": "0001045810",   # NVIDIA Corp
    "TSLA": "0001318605",   # Tesla Inc
}
"""SEC requires CIK as a 10-digit zero-padded string in URLs."""
