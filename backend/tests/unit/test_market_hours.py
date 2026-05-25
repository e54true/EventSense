"""Unit tests for is_market_open() — covers DST + weekend boundaries."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.lib.market_hours import is_market_open

EASTERN = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def _et(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Build a tz-aware Eastern Time datetime for test inputs."""
    return datetime(year, month, day, hour, minute, tzinfo=EASTERN)


def test_open_during_regular_trading_hours_summer() -> None:
    # July → EDT (UTC-4). 10:00 AM ET on a Wednesday.
    assert is_market_open(_et(2026, 7, 15, 10, 0))


def test_open_during_regular_trading_hours_winter() -> None:
    # January → EST (UTC-5). 10:00 AM ET on a Wednesday.
    assert is_market_open(_et(2026, 1, 14, 10, 0))


def test_closed_before_open() -> None:
    assert not is_market_open(_et(2026, 1, 14, 9, 29))


def test_open_at_open_bell() -> None:
    assert is_market_open(_et(2026, 1, 14, 9, 30))


def test_closed_at_close_bell() -> None:
    # 16:00:00 sharp counts as closed (interval is [open, close))
    assert not is_market_open(_et(2026, 1, 14, 16, 0))


def test_closed_on_saturday() -> None:
    # 2026-01-10 = Saturday
    assert not is_market_open(_et(2026, 1, 10, 12, 0))


def test_closed_on_sunday() -> None:
    # 2026-01-11 = Sunday
    assert not is_market_open(_et(2026, 1, 11, 12, 0))


def test_accepts_utc_input_and_converts() -> None:
    # 14:30 UTC on a Wednesday = 9:30 ET (EST) or 10:30 ET (EDT depending on date)
    # Use winter so we know UTC-5 → 9:30 ET
    utc = datetime(2026, 1, 14, 14, 30, tzinfo=UTC)
    assert is_market_open(utc)
