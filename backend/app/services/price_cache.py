"""Redis cache for the latest price per ticker.

Why Redis: the GET /prices/{ticker}/latest endpoint and (future) LLM analyzer
both want "the most recent price for AAPL" without paying a Postgres round
trip every time. yfinance itself has informal rate limits, so caching also
shields us from over-polling.

Cache key shape:    eventsense:latest_price:{TICKER}     (str)
Cache value:        the price as a string (Decimal-safe)
TTL:                60 seconds

We expose a thin functional API rather than a class so the redis client lives
as a module singleton — one connection pool, lazy-initialized.
"""

from decimal import Decimal

import redis.asyncio as redis_async
import structlog

from app.config.settings import get_settings

logger = structlog.get_logger(__name__)

_CACHE_TTL_SECONDS = 60
_KEY_PREFIX = "eventsense:latest_price:"

# Module-level singleton — redis-py's async client manages its own pool internally.
# Created lazily so that test code that doesn't touch the cache doesn't need Redis up.
_client: redis_async.Redis | None = None


def _get_client() -> redis_async.Redis:
    global _client
    if _client is None:
        _client = redis_async.from_url(
            get_settings().redis_url,
            decode_responses=True,  # strings in, strings out
        )
    return _client


def _key(ticker: str) -> str:
    return f"{_KEY_PREFIX}{ticker.upper()}"


async def cache_latest_price(ticker: str, price: Decimal) -> None:
    """Store the latest price for `ticker`; expires after 60s."""
    try:
        await _get_client().set(_key(ticker), str(price), ex=_CACHE_TTL_SECONDS)
    except Exception as exc:
        logger.warning("price_cache.set.failed", ticker=ticker, error=str(exc))


async def get_latest_price(ticker: str) -> Decimal | None:
    """Return cached price, or None on miss / Redis outage."""
    try:
        raw = await _get_client().get(_key(ticker))
    except Exception as exc:
        logger.warning("price_cache.get.failed", ticker=ticker, error=str(exc))
        return None
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except Exception:
        return None
