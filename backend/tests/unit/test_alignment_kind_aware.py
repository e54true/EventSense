"""Tests for kind-aware is_aligned behavior.

The headline change in Phase 4: MARKET predictions (especially SPY-vs-SPY)
should align on raw market return, NOT on excess-vs-SPY (which is
definitionally 0 for SPY itself).
"""

from app.db.models import PredictionDirection, PredictionKind
from app.services.alignment import is_aligned

# When excess and raw_return diverge, kind picks which yardstick wins.
# Imagine SPY went up 0.6% and so did the prediction's ticker (e.g. another SPY
# call) — excess is 0, raw_return is +0.006.
_SPY_UP_DAY = {"excess": 0.0, "raw_return": 0.006}
_SPY_DOWN_DAY = {"excess": 0.0, "raw_return": -0.008}
_SPY_FLAT_DAY = {"excess": 0.0, "raw_return": 0.002}


def test_company_predictions_still_use_excess() -> None:
    """COMPANY kind unchanged from v1: excess is the yardstick."""
    # Stock outperformed SPY by +1.2% — bullish call aligns
    assert is_aligned(
        PredictionDirection.BULLISH,
        excess=0.012,
        kind=PredictionKind.COMPANY,
        raw_return=0.005,  # raw_return should be ignored for COMPANY
    )
    # Same scenario but BEARISH call → misaligned
    assert not is_aligned(
        PredictionDirection.BEARISH,
        excess=0.012,
        kind=PredictionKind.COMPANY,
        raw_return=0.005,
    )


def test_market_spy_bullish_with_market_up_is_aligned() -> None:
    """SPY MARKET BULLISH on a +0.6% SPY day — excess is 0, but we should align."""
    assert is_aligned(
        PredictionDirection.BULLISH,
        excess=_SPY_UP_DAY["excess"],
        kind=PredictionKind.MARKET,
        raw_return=_SPY_UP_DAY["raw_return"],
    )


def test_market_spy_bullish_with_market_down_is_misaligned() -> None:
    """SPY MARKET BULLISH but market fell — not aligned (raw_return < 0)."""
    assert not is_aligned(
        PredictionDirection.BULLISH,
        excess=_SPY_DOWN_DAY["excess"],
        kind=PredictionKind.MARKET,
        raw_return=_SPY_DOWN_DAY["raw_return"],
    )


def test_market_spy_neutral_with_small_move_is_aligned() -> None:
    """SPY MARKET NEUTRAL with |raw_return| < 0.5% → aligned."""
    assert is_aligned(
        PredictionDirection.NEUTRAL,
        excess=_SPY_FLAT_DAY["excess"],
        kind=PredictionKind.MARKET,
        raw_return=_SPY_FLAT_DAY["raw_return"],
    )


def test_market_spy_neutral_with_large_move_is_misaligned() -> None:
    """SPY MARKET NEUTRAL but market jumped 0.8% → not aligned."""
    assert not is_aligned(
        PredictionDirection.NEUTRAL,
        excess=0.0,
        kind=PredictionKind.MARKET,
        raw_return=0.008,
    )


def test_market_qqq_bullish_uses_raw_return_not_excess() -> None:
    """Even when QQQ excess is negative (underperformed SPY), if QQQ itself rallied,
    a BULLISH MARKET call on QQQ should align — user-facing semantic is "the index
    went up", not "the index outperformed SPY."""
    # QQQ +0.4%, SPY +0.6% → excess = -0.2%, but QQQ went up
    assert is_aligned(
        PredictionDirection.BULLISH,
        excess=-0.002,
        kind=PredictionKind.MARKET,
        raw_return=0.004,
    )


def test_default_kind_company_unchanged() -> None:
    """Callers that don't pass kind/raw_return get v1 behavior (excess-only)."""
    assert is_aligned(PredictionDirection.BULLISH, excess=0.01)
    assert not is_aligned(PredictionDirection.BULLISH, excess=-0.01)
