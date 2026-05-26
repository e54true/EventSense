"""Unit tests for the LLM output Pydantic schemas — proves validation gates work."""

import pytest
from pydantic import ValidationError

from app.llm.schemas import EventAnalysis, TickerImpact


def test_ticker_impact_accepts_valid() -> None:
    t = TickerImpact(
        ticker="AAPL",
        direction="BULLISH",
        magnitude="MEDIUM",
        confidence=0.7,
        reasoning="Beat estimates; iPhone strong.",
    )
    assert t.confidence == 0.7


def test_ticker_impact_rejects_confidence_out_of_range() -> None:
    with pytest.raises(ValidationError):
        TickerImpact(
            ticker="AAPL",
            direction="BULLISH",
            magnitude="MEDIUM",
            confidence=1.5,  # too high
            reasoning="x",
        )


def test_ticker_impact_rejects_unknown_direction() -> None:
    with pytest.raises(ValidationError):
        TickerImpact(
            ticker="AAPL",
            direction="MOON",  # not in Literal
            magnitude="HIGH",
            confidence=0.9,
            reasoning="x",
        )


def test_event_analysis_empty_impacts_ok() -> None:
    """A valid analysis can have zero impacts — means 'event affects nothing on watchlist'."""
    a = EventAnalysis(summary="Routine 8-K with no material info.", impacts=[])
    assert a.impacts == []


def test_event_analysis_summary_length_capped() -> None:
    with pytest.raises(ValidationError):
        EventAnalysis(summary="x" * 201, impacts=[])
