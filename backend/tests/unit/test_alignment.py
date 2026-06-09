"""Unit tests for alignment math — pure functions, no DB, no mocks."""

import pytest

from app.db.models import PredictionDirection
from app.services.alignment import (
    NEUTRAL_THRESHOLD,
    excess_return,
    is_aligned,
    ticker_return,
)

# --- ticker_return ---


def test_ticker_return_positive_move() -> None:
    assert ticker_return(100.0, 102.0) == pytest.approx(0.02)


def test_ticker_return_negative_move() -> None:
    assert ticker_return(100.0, 98.0) == pytest.approx(-0.02)


def test_ticker_return_zero_change() -> None:
    assert ticker_return(100.0, 100.0) == 0.0


def test_ticker_return_raises_on_zero_baseline() -> None:
    with pytest.raises(ValueError, match="non-positive"):
        ticker_return(0.0, 100.0)


def test_ticker_return_raises_on_negative_baseline() -> None:
    with pytest.raises(ValueError):
        ticker_return(-1.0, 100.0)


# --- excess_return ---


def test_excess_return_outperformed_market() -> None:
    # Ticker +3%, SPY +1% → excess +2%
    assert excess_return(0.03, 0.01) == pytest.approx(0.02)


def test_excess_return_underperformed_market() -> None:
    # Ticker -1%, SPY +1% → excess -2%
    assert excess_return(-0.01, 0.01) == pytest.approx(-0.02)


def test_excess_return_followed_market_exactly() -> None:
    assert excess_return(0.015, 0.015) == 0.0


# --- is_aligned ---


class TestBullishAlignment:
    def test_aligned_when_move_above_threshold(self) -> None:
        assert is_aligned(PredictionDirection.BULLISH, 0.02) is True

    def test_not_aligned_when_move_zero(self) -> None:
        assert is_aligned(PredictionDirection.BULLISH, 0.0) is False

    def test_not_aligned_when_move_negative(self) -> None:
        assert is_aligned(PredictionDirection.BULLISH, -0.01) is False

    def test_not_aligned_when_small_positive_under_threshold(self) -> None:
        # +0.3% is positive but under the 0.5% threshold → BULLISH not aligned
        # (would have been the right call only if predicted NEUTRAL).
        assert is_aligned(PredictionDirection.BULLISH, 0.003) is False


class TestBearishAlignment:
    def test_aligned_when_move_below_neg_threshold(self) -> None:
        assert is_aligned(PredictionDirection.BEARISH, -0.02) is True

    def test_not_aligned_when_move_zero(self) -> None:
        assert is_aligned(PredictionDirection.BEARISH, 0.0) is False

    def test_not_aligned_when_move_positive(self) -> None:
        assert is_aligned(PredictionDirection.BEARISH, 0.01) is False

    def test_not_aligned_when_small_negative_above_neg_threshold(self) -> None:
        # -0.3% is negative but within ±0.5% threshold → BEARISH not aligned.
        assert is_aligned(PredictionDirection.BEARISH, -0.003) is False


class TestNeutralAlignment:
    def test_aligned_when_move_under_threshold(self) -> None:
        # 0.3% < 0.5% threshold → NEUTRAL was right
        assert is_aligned(PredictionDirection.NEUTRAL, 0.003) is True

    def test_aligned_when_small_negative_move(self) -> None:
        assert is_aligned(PredictionDirection.NEUTRAL, -0.003) is True

    def test_aligned_at_exactly_zero(self) -> None:
        assert is_aligned(PredictionDirection.NEUTRAL, 0.0) is True

    def test_not_aligned_when_big_positive_move(self) -> None:
        # NEUTRAL predicted but ticker jumped 2% → wrong
        assert is_aligned(PredictionDirection.NEUTRAL, 0.02) is False

    def test_not_aligned_at_exactly_threshold(self) -> None:
        # Boundary: at the threshold (not <) → not aligned
        assert is_aligned(PredictionDirection.NEUTRAL, NEUTRAL_THRESHOLD) is False
