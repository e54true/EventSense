"""Integration test: FRED adapter must be idempotent.

Calling fetch_cpi twice with the same observations should insert N rows the first
time and 0 rows the second time. The (source, external_id) unique constraint is the
safety net; the pre-check SELECT is the optimization.

Requires a running Postgres (docker compose up postgres).
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.fred import fetch_cpi
from app.db.models import Event, EventSource


@pytest.fixture(autouse=True)
def _set_fred_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key-12345")
    from app.config.settings import get_settings

    get_settings.cache_clear()


SAMPLE_OBSERVATIONS = [
    {"date": "2026-04-01", "value": "332.407"},
    {"date": "2026-03-01", "value": "330.293"},
    {"date": "2026-02-01", "value": "327.460"},
]


async def _count_fred_events(db: AsyncSession) -> int:
    result = await db.scalar(
        select(func.count()).select_from(Event).where(Event.source == EventSource.FRED)
    )
    return result or 0


async def test_fetch_cpi_is_idempotent(db_session: AsyncSession) -> None:
    with patch(
        "app.adapters.fred._fetch_series_observations",
        new=AsyncMock(return_value=SAMPLE_OBSERVATIONS),
    ):
        inserted_first = await fetch_cpi(db_session)
        inserted_second = await fetch_cpi(db_session)

    assert inserted_first == 3
    assert inserted_second == 0
    assert await _count_fred_events(db_session) == 3


async def test_fetch_cpi_writes_expected_fields(db_session: AsyncSession) -> None:
    with patch(
        "app.adapters.fred._fetch_series_observations",
        new=AsyncMock(return_value=[SAMPLE_OBSERVATIONS[0]]),
    ):
        await fetch_cpi(db_session)

    row = await db_session.scalar(select(Event).where(Event.source == EventSource.FRED))
    assert row is not None
    assert row.external_id == "CPIAUCSL:2026-04-01"
    assert row.event_type == "ECONOMIC_RELEASE"
    assert row.payload["series_id"] == "CPIAUCSL"
    assert row.payload["value"] == 332.407
    assert row.status.value == "FETCHED"
