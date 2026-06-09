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


def test_event_analysis_summary_length_capped_at_800() -> None:
    """v3.2 bumped summary from 200→800 chars to fit the thesis-paragraph
    structure the prompt now asks for."""
    # 800 still fits
    EventAnalysis(summary="x" * 800, impacts=[])
    # 801 doesn't
    with pytest.raises(ValidationError):
        EventAnalysis(summary="x" * 801, impacts=[])


def test_ticker_impact_reasoning_capped_at_2000() -> None:
    """v3.2 bumped per-impact reasoning from 500→2000 chars."""
    TickerImpact(
        ticker="AAPL",
        direction="BULLISH",
        magnitude="MEDIUM",
        confidence=0.7,
        reasoning="x" * 2000,
    )
    with pytest.raises(ValidationError):
        TickerImpact(
            ticker="AAPL",
            direction="BULLISH",
            magnitude="MEDIUM",
            confidence=0.7,
            reasoning="x" * 2001,
        )
