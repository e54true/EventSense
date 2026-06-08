"""Unit tests for document_fetcher — HTML strip + EX-99.x filename matching.

End-to-end DB persistence is covered by tests/integration/test_documents.py.
"""

from app.adapters.fred import _fetch_series_observations  # noqa: F401 — import sanity
from app.services.document_fetcher import _EX99_PATTERN, _strip_html

_FILING_HTML = """
<html><head><script>tracker()</script><style>body{}</style></head>
<body>
<nav>top nav links to skip</nav>
<div>
<h2>Item 5.02 Departure of Directors or Certain Officers</h2>
<p>On May 30, 2026, John Doe notified the Board of Directors of his decision
to retire from his position as Chief Financial Officer effective immediately,
to pursue other opportunities. Mr Doe has served as CFO since 2018 and the
Board thanks him for his service.</p>
<p>The Board has appointed Jane Smith as interim Chief Financial Officer
while the company conducts a search for a permanent replacement. Ms Smith has
served as Vice President of Finance since 2022 and brings substantial expertise
to the role.</p>
</div>
<footer>SEC boilerplate copyright notice</footer>
</body></html>
"""

_TOO_SHORT_HTML = "<html><body><p>404 not found</p></body></html>"


def test_strip_html_removes_script_style_nav_footer() -> None:
    text = _strip_html(_FILING_HTML)
    assert text is not None
    assert "John Doe notified the Board" in text
    assert "Jane Smith" in text
    # Noise tags removed
    assert "tracker()" not in text
    assert "top nav" not in text
    assert "SEC boilerplate" not in text


def test_strip_html_returns_none_for_short_content() -> None:
    """Pages with <200 chars of text are treated as stubs / error pages."""
    assert _strip_html(_TOO_SHORT_HTML) is None


def test_ex99_pattern_matches_common_naming_conventions() -> None:
    """SEC filings use many EX-99.x filename variants; pattern must cover them."""
    matches = [
        "ex991.htm",
        "ex99-1.htm",
        "ex99.1.htm",
        "ex-99-1.htm",
        "ex_99_1.htm",
        "Exhibit991.htm",
        "EXHIBIT99-1.HTM",
    ]
    for name in matches:
        assert _EX99_PATTERN.match(name), f"should match: {name}"

    non_matches = [
        "goog-20260602.htm",  # primary doc
        "ex101.htm",  # EX-10.1 (employment agreement) — not 99.x
        "ex2.htm",
        "FilingSummary.xml",
        "primary.htm",
    ]
    for name in non_matches:
        assert not _EX99_PATTERN.match(name), f"should NOT match: {name}"
