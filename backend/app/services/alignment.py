"""Pure functions for prediction alignment + return math.

Kept separate from the validator orchestration so the trickiest logic (sign
matching, neutral threshold) is trivially unit-testable without DB / mocks.

Sign convention:
  excess_return > 0  → ticker outperformed SPY → BULLISH was right
  excess_return < 0  → ticker underperformed SPY → BEARISH was right
  |excess_return| < NEUTRAL_THRESHOLD → no meaningful move → NEUTRAL was right
"""

from app.db.models import PredictionDirection, PredictionKind

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


def is_aligned(
    direction: PredictionDirection,
    excess: float,
    *,
    kind: PredictionKind = PredictionKind.COMPANY,
    raw_return: float | None = None,
) -> bool:
    """Did the prediction match reality?

    For `kind=COMPANY`, we compare against `excess` (alpha vs SPY) — same
    semantics as v1. This rewards stock-picking signal beyond the broad market.

    For `kind=MARKET` (SPY/QQQ predictions), we compare against `raw_return`
    instead. SPY-vs-SPY excess is definitionally 0, which would force all SPY
    MARKET predictions into NEUTRAL alignment regardless of the actual move —
    not what we want. We want "did the market go up like you said?". QQQ
    technically *could* still use excess (tech tilt is a real bet), but the
    user-facing semantic of a MARKET prediction is "the index will move
    direction X", so raw return is the honest yardstick for both.

    Truth table (per the chosen yardstick):
        BULLISH + yardstick > 0           → aligned
        BEARISH + yardstick < 0           → aligned
        NEUTRAL + |yardstick| < threshold → aligned
    """
    yardstick = raw_return if kind == PredictionKind.MARKET and raw_return is not None else excess

    if direction == PredictionDirection.BULLISH:
        return yardstick > 0
    if direction == PredictionDirection.BEARISH:
        return yardstick < 0
    return abs(yardstick) < NEUTRAL_THRESHOLD
