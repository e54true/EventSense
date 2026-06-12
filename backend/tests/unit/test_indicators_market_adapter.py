"""Unit tests for the multpl.com market-indicators adapter.

We avoid the real network by patching the async _fetch_html helper to return
hand-shaped HTML that matches multpl's structure.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.indicators_market import (
    MULTPL_SPECS,
    _parse_current_value,
    fetch_new,
)

_PE_HTML = """
<html><body>
<div id="current">
<b>Current<span class="currentTitle">
S&P 500 PE Ratio</span>:</b>
31.83
<span class="neg">-0.86 (-2.64%)</span>
<div id="timestamp">4:00 PM EDT, Fri Jun 5</div>
</div>
</body></html>
"""

_EPS_HTML = """
<html><body>
<div id="current">
<b>Current<span class="currentTitle"> 12 month EPS</span>:</b>
239.98
<div id="timestamp">Reported Sep 2025</div>
</div>
</body></html>
"""

_NO_CURRENT_DIV = "<html><body><p>page broke</p></body></html>"

_WITH_PERCENT_SUFFIX = """
<div id="current">
<b>Current<span class="currentTitle"> S&P 500 Earnings Yield</span>:</b>
3.14%
</div>
"""


def test_parse_current_value_handles_pe_block() -> None:
    assert _parse_current_value(_PE_HTML) == pytest.approx(31.83)


def test_parse_current_value_handles_eps_block() -> None:
    assert _parse_current_value(_EPS_HTML) == pytest.approx(239.98)


def test_parse_current_value_strips_percent_suffix() -> None:
    """If multpl returns a value with a trailing %, we should still parse the number."""
    assert _parse_current_value(_WITH_PERCENT_SUFFIX) == pytest.approx(3.14)


def test_parse_current_value_returns_none_when_no_block() -> None:
    assert _parse_current_value(_NO_CURRENT_DIV) is None


async def test_fetch_new_emits_one_observation_per_spec() -> None:
    """Each MultplSpec URL → one IndicatorObservation when parse succeeds."""
    html_per_url = {
        "https://www.multpl.com/s-p-500-pe-ratio": _PE_HTML,
        "https://www.multpl.com/s-p-500-earnings": _EPS_HTML,
    }
    with patch(
        "app.adapters.indicators_market._fetch_html",
        new=AsyncMock(side_effect=lambda url: html_per_url.get(url)),
    ):
        obs = await fetch_new()

    assert len(obs) == len(MULTPL_SPECS)
    by_key = {o.indicator_key: o for o in obs}
    assert by_key["SP500_PE"].value == pytest.approx(31.83)
    assert by_key["SP500_TTM_EPS"].value == pytest.approx(239.98)
    assert all(o.source == "MULTPL" for o in obs)


async def test_fetch_new_skips_failed_pages() -> None:
    """If a URL fetch returns None (network error), that spec is skipped — others still emit."""
    with patch(
        "app.adapters.indicators_market._fetch_html",
        new=AsyncMock(
            side_effect=lambda url: _PE_HTML if "pe-ratio" in url else None  # earnings page "fails"
        ),
    ):
        obs = await fetch_new()
    assert len(obs) == 1
    assert obs[0].indicator_key == "SP500_PE"


async def test_fetch_new_skips_unparseable_pages() -> None:
    """Empty-content / format-broken pages skip without crashing."""
    with patch(
        "app.adapters.indicators_market._fetch_html",
        new=AsyncMock(return_value=_NO_CURRENT_DIV),
    ):
        obs = await fetch_new()
    assert obs == []
