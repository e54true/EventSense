"""Pure functions for prediction alignment + return math.

Kept separate from the validator orchestration so the trickiest logic (sign
matching, neutral threshold) is trivially unit-testable without DB / mocks.

Sign convention (post-simplification):
  raw_return > +threshold  → ticker went up   → BULLISH was right
  raw_return < -threshold  → ticker went down → BEARISH was right
  |raw_return| < threshold → no meaningful move → NEUTRAL was right

The excess-vs-SPY framing was dropped: it produced confusing results for
MARKET predictions (SPY-vs-SPY excess is always 0) and the cleaner UX is
"did the stock move as predicted, in absolute terms". excess_return is
still computed and stored on prediction_outcomes for analytics, but not
used to decide aligned.

The neutral threshold scales with the window length: equity volatility grows
roughly with √t, so a flat 0.5% band that's reasonable for 24h makes NEUTRAL
nearly auto-wrong at 7d (SPY moves >0.5% most weeks). 7d uses 1.5% ≈
0.5% x √(7 trading-day-ish horizon), rounded to a clean number.
"""

from app.db.models import OutcomeWindow, PredictionDirection

# Per-window NEUTRAL bands. NEUTRAL aligns only when |actual move| stays under
# the threshold; above it we expect a directional call.
NEUTRAL_THRESHOLDS: dict[OutcomeWindow, float] = {
    OutcomeWindow.H1: 0.002,  # legacy window — kept for completeness
    OutcomeWindow.H24: 0.005,
    OutcomeWindow.D7: 0.015,
}

# Back-compat alias — the 24h band is the historical default and is still
# referenced by the v3 prompt text + docs.
NEUTRAL_THRESHOLD = NEUTRAL_THRESHOLDS[OutcomeWindow.H24]


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


def is_aligned(
    direction: PredictionDirection,
    raw_return: float,
    window: OutcomeWindow = OutcomeWindow.H24,
) -> bool:
    """Did the prediction match reality over `window`?

    Truth table (t = NEUTRAL_THRESHOLDS[window]):
        BULLISH + raw_return > +t  → aligned
        BEARISH + raw_return < -t  → aligned
        NEUTRAL + |raw_return| < t → aligned
        anything else              → not aligned

    Knife-edge note: at |raw_return| == t exactly, neither BULLISH/BEARISH
    (need strict >) nor NEUTRAL (needs strict <) is aligned. Acceptable for
    a floating-point boundary case.
    """
    threshold = NEUTRAL_THRESHOLDS[window]
    if direction == PredictionDirection.BULLISH:
        return raw_return > threshold
    if direction == PredictionDirection.BEARISH:
        return raw_return < -threshold
    return abs(raw_return) < threshold
