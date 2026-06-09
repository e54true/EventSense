"""Pure functions for prediction alignment + return math.

Kept separate from the validator orchestration so the trickiest logic (sign
matching, neutral threshold) is trivially unit-testable without DB / mocks.

Sign convention (post-simplification):
  raw_return > +NEUTRAL_THRESHOLD  → ticker went up   → BULLISH was right
  raw_return < -NEUTRAL_THRESHOLD  → ticker went down → BEARISH was right
  |raw_return| < NEUTRAL_THRESHOLD → no meaningful move → NEUTRAL was right

The excess-vs-SPY framing was dropped: it produced confusing results for
MARKET predictions (SPY-vs-SPY excess is always 0) and the cleaner UX is
"did the stock move as predicted, in absolute terms". excess_return is
still computed and stored on prediction_outcomes for analytics, but not
used to decide aligned.
"""

from app.db.models import PredictionDirection

# NEUTRAL aligns only when |actual move| stays under this threshold; above it
# we expect a directional call. 0.5% = the per-spec §6.4 default; bump in
# settings later if intra-day noise warrants.
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
    """Active return vs the SPY benchmark — stored for analytics, no longer
    used to decide aligned. See module docstring."""
    return ticker_ret - spy_ret


def is_aligned(direction: PredictionDirection, raw_return: float) -> bool:
    """Did the prediction match reality?

    Truth table:
        BULLISH + raw_return > +NEUTRAL_THRESHOLD  → aligned
        BEARISH + raw_return < -NEUTRAL_THRESHOLD  → aligned
        NEUTRAL + |raw_return| < NEUTRAL_THRESHOLD → aligned
        anything else                              → not aligned

    Knife-edge note: at |raw_return| == NEUTRAL_THRESHOLD exactly, neither
    BULLISH/BEARISH (need strict >) nor NEUTRAL (needs strict <) is aligned.
    Acceptable for a floating-point boundary case.
    """
    if direction == PredictionDirection.BULLISH:
        return raw_return > NEUTRAL_THRESHOLD
    if direction == PredictionDirection.BEARISH:
        return raw_return < -NEUTRAL_THRESHOLD
    return abs(raw_return) < NEUTRAL_THRESHOLD
