"""Unit tests for the FOMC dot plot (SEP) adapter — frozen HTML fixtures, no network."""

from unittest.mock import AsyncMock, patch

from app.adapters.dot_plot import (
    _extract_release_dates,
    _parse_projection_table,
    fetch_new,
)
from app.db.models import EventSource

_CALENDARS_HTML = """
<html><body>
<a href="/monetarypolicy/fomcprojtabl20260318.htm">PDF</a>
<a href="/monetarypolicy/fomcprojtabl20251210.htm">PDF</a>
<a href="/monetarypolicy/fomcprojtabl20250917.htm">PDF</a>
</body></html>
"""

_SEP_HTML = """
<html><body>
<table>
<tr><th>Variable</th><th>Median</th><th>Central Tendency</th><th>Range</th></tr>
<tr>
  <th></th>
  <th>2026</th><th>2027</th><th>2028</th><th>Longer run</th>
  <th>2026</th><th>2027</th><th>2028</th><th>Longer run</th>
  <th>2026</th><th>2027</th><th>2028</th><th>Longer run</th>
</tr>
<tr>
  <td>Change in real GDP</td>
  <td>2.4</td><td>2.3</td><td>2.1</td><td>2.0</td>
  <td>2.2-2.5</td><td>2.0-2.4</td><td>2.0-2.3</td><td>1.8-2.0</td>
  <td>2.1-2.7</td><td>2.0-2.7</td><td>1.8-2.7</td><td>1.7-2.5</td>
</tr>
<tr>
  <td>Federal funds rate</td>
  <td>3.4</td><td>3.1</td><td>3.1</td><td>3.1</td>
  <td>3.1-3.6</td><td>2.9-3.6</td><td>2.9-3.6</td><td>2.9-3.5</td>
  <td>2.6-3.6</td><td>2.4-3.9</td><td>2.6-3.9</td><td>2.6-3.9</td>
</tr>
</table>
</body></html>
"""

_SEP_HTML_NO_FED_FUNDS = """
<html><body>
<table>
<tr><th>Variable</th><th>Median</th></tr>
<tr><th></th><th>2026</th><th>2027</th><th>2028</th><th>Longer run</th>
<th>2026</th><th>2027</th><th>2028</th><th>Longer run</th>
<th>2026</th><th>2027</th><th>2028</th><th>Longer run</th></tr>
<tr><td>Unemployment rate</td><td>4.4</td><td>4.3</td><td>4.2</td><td>4.2</td>
<td>4.3-4.5</td><td>4.2-4.4</td><td>4.0-4.4</td><td>4.0-4.3</td>
<td>4.3-4.6</td><td>4.0-4.5</td><td>4.0-4.5</td><td>3.8-4.5</td></tr>
</table>
</body></html>
"""


def test_extract_release_dates_returns_unique_sorted_descending() -> None:
    dates = _extract_release_dates(_CALENDARS_HTML)
    assert dates == ["20260318", "20251210", "20250917"]


def test_parse_projection_table_extracts_fed_funds_row() -> None:
    result = _parse_projection_table(_SEP_HTML)
    assert result is not None
    assert result["median"] == {
        "2026": "3.4",
        "2027": "3.1",
        "2028": "3.1",
        "Longer run": "3.1",
    }
    assert result["central_tendency"]["2026"] == "3.1-3.6"
    assert result["range"]["Longer run"] == "2.6-3.9"


def test_parse_projection_table_returns_none_without_fed_funds_row() -> None:
    """If the SEP HTML is missing the federal funds row entirely, return None."""
    assert _parse_projection_table(_SEP_HTML_NO_FED_FUNDS) is None


async def test_fetch_new_emits_one_event_per_release() -> None:
    """Calendar lists 3 SEPs → adapter returns 3 RawEvents."""

    async def _fake_html(url: str) -> str:
        if url.endswith("fomccalendars.htm"):
            return _CALENDARS_HTML
        return _SEP_HTML  # every individual SEP page returns the canned table

    with patch("app.adapters.dot_plot._fetch_html", new=AsyncMock(side_effect=_fake_html)):
        events = await fetch_new()

    assert len(events) == 3
    assert all(e.source == EventSource.FOMC for e in events)
    assert all(e.event_type == "DOT_PLOT_RELEASE" for e in events)
    assert {e.external_id for e in events} == {"20260318", "20251210", "20250917"}

    first = next(e for e in events if e.external_id == "20260318")
    assert first.payload["fed_funds_rate"]["median"]["2026"] == "3.4"
    assert first.published_at.date().isoformat() == "2026-03-18"


async def test_fetch_new_returns_empty_when_calendar_fetch_fails() -> None:
    """If the FOMC calendars page is unreachable, return [] gracefully."""
    with patch("app.adapters.dot_plot._fetch_html", new=AsyncMock(return_value=None)):
        events = await fetch_new()
    assert events == []


async def test_fetch_new_skips_unparseable_sep_page() -> None:
    """If one SEP page is broken, others still emit; broken one is skipped."""

    async def _fake_html(url: str) -> str:
        if url.endswith("fomccalendars.htm"):
            return _CALENDARS_HTML
        if "20251210" in url:
            return _SEP_HTML_NO_FED_FUNDS  # this one is broken
        return _SEP_HTML

    with patch("app.adapters.dot_plot._fetch_html", new=AsyncMock(side_effect=_fake_html)):
        events = await fetch_new()

    assert len(events) == 2
    assert "20251210" not in {e.external_id for e in events}
