"""US equity market hours: 9:30 AM - 4:00 PM ET, Mon-Fri.

The Eastern Time zone shifts between EST (UTC-5) and EDT (UTC-4) twice a year,
so we use a real tz database (Python 3.9+ stdlib `zoneinfo`) rather than
hardcoding a UTC offset. Stale offsets caused at least one famous trading bug
(Knight Capital didn't crash on this, but plenty of smaller shops have).

We deliberately don't handle market holidays here — adding the full NYSE
holiday calendar would pull in pandas_market_calendars (~50MB of deps). For
M4 the cost of fetching prices on a closed-but-not-weekend day is a few
no-op API calls per year, which is fine.
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)


def is_market_open(now: datetime | None = None) -> bool:
    """Return True if US equity markets are open right now (weekday + hours).

    `now` defaults to current time (timezone-aware in UTC); injectable for tests.
    """
    if now is None:
        now = datetime.now(ZoneInfo("UTC"))
    et_now = now.astimezone(EASTERN)
    if et_now.weekday() >= 5:  # 5=Sat, 6=Sun
        return False
    return MARKET_OPEN <= et_now.time() < MARKET_CLOSE
