"""Pure functions for prediction alignment + return math.

Kept separate from the validator orchestration so the trickiest logic (sign
matching, neutral threshold) is trivially unit-testable without DB / mocks.

Sign convention:
  excess_return > 0  → ticker outperformed SPY → BULLISH was right
  excess_return < 0  → ticker underperformed SPY → BEARISH was right
  |excess_return| < NEUTRAL_THRESHOLD → no meaningful move → NEUTRAL was right
"""

from app.db.models import PredictionDirection

# Per spec §6.4: NEUTRAL aligns only when the actual move is under 0.5%.
# Above that, we count it as a wrong "no movement" call.
NEUTRAL_THRESHOLD = 0.005


def ticker_return(baseline: float, end: float) -> float:
    """Simple percent change as a decimal. (end - baseline) / baseline.

    Both inputs are expected to be > 0 (real prices). If baseline is 0 we'd
    divide by zero — callers should never pass that in, but we surface the
    error rather than silently returning inf.
    """
    if baseline <= 0:
        raise ValueError(f"Cannot compute return with non-positive baseline {baseline}")
    return (end - baseline) / baseline


def excess_return(ticker_ret: float, spy_ret: float) -> float:
    """Active return vs the SPY benchmark — what the ticker did beyond the broad market."""
    return ticker_ret - spy_ret


def is_aligned(direction: PredictionDirection, excess: float) -> bool:
    """Did the prediction match reality (in direction, controlling for the market)?

    Truth table:
        BULLISH + excess > 0           → aligned
        BEARISH + excess < 0           → aligned
        NEUTRAL + |excess| < threshold → aligned
        anything else                  → not aligned
    """
    if direction == PredictionDirection.BULLISH:
        return excess > 0
    if direction == PredictionDirection.BEARISH:
        return excess < 0
    # NEUTRAL: aligned only if the move was small enough to count as "no movement"
    return abs(excess) < NEUTRAL_THRESHOLD
