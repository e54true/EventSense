"""Pydantic schemas the LLM must return, enforced by `instructor`.

These are the wire contract between the model and the analyzer. instructor
inspects them, builds a JSON schema, attaches it as a function/tool definition
to the OpenAI/Anthropic call, then validates the response back into these
classes — retrying up to N times if the model emits malformed JSON.

Per spec §9, every field is constrained tightly:
- direction / magnitude are enums so the LLM can't invent "MAYBE_UP"
- confidence is bounded to [0, 1]
- reasoning is capped so we don't pay for a 5000-token essay per ticker
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TickerImpact(BaseModel):
    """One ticker's predicted reaction to an event.

    `kind` distinguishes broad-market calls (SPY/QQQ) from per-company calls.
    v1 prompt clients never set this — the v1 LLM only emitted per-company
    impacts; the analyzer defaults their `kind` to COMPANY when persisting.
    v2 prompt clients must always set it; the analyzer validates ticker
    correctness against the kind (MARKET ⇒ {SPY, QQQ}; COMPANY ⇒ event's
    affected ticker).
    """

    model_config = ConfigDict(frozen=True)

    ticker: str = Field(min_length=1, max_length=10)
    # Default COMPANY for v1 prompt back-compat; v2 prompt instructs the LLM
    # to set it explicitly.
    kind: Literal["MARKET", "COMPANY"] = "COMPANY"
    # 24h call. The v3 prompt scores this against the raw 24h return.
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    # Separate 7-day call (v3+). The 24h impulse and week-out drift can
    # legitimately differ. None = older prompt versions that didn't ask.
    direction_7d: Literal["BULLISH", "BEARISH", "NEUTRAL"] | None = None
    magnitude: Literal["LOW", "MEDIUM", "HIGH"]
    # Confidence about direction, not magnitude. 0.5 = coin flip; values
    # below 0.5 are clamped conceptually meaningless — the prompt anchors
    # the scale at [0.5, 1.0].
    confidence: float = Field(ge=0.0, le=1.0)
    # 3-5 sentences explaining THIS ticker's specific reasoning (not a repeat
    # of the EventAnalysis-level summary). The cap is generous because v3.2
    # asks the LLM to cover mechanism + confidence rationale + counter-thesis.
    reasoning: str = Field(min_length=1, max_length=2000)


class EventAnalysis(BaseModel):
    """Full LLM output for one event."""

    model_config = ConfigDict(frozen=True)

    # Overall thesis paragraph displayed prominently on the website for human
    # review — covers what happened, key context, historical regime anchor,
    # net bias, and the biggest uncertainty. v3.2 expanded from 200 → 800 to
    # accommodate the structured walkthrough the prompt asks for.
    summary: str = Field(min_length=1, max_length=800)
    # Per-ticker impacts. Empty list is valid — means "this event affects nothing
    # on our watchlist meaningfully" (e.g. a random 8-K with item 8.01 boilerplate).
    impacts: list[TickerImpact] = Field(default_factory=list)
