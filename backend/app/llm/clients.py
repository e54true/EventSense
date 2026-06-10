"""Provider-agnostic async LLM client wrapper.

`instructor` patches the official OpenAI / Anthropic SDKs so they return
Pydantic models directly. If the model emits invalid JSON, instructor retries
internally (up to N times) by re-prompting with the validation error message.

We expose one function — `analyze_event()` — that hides which provider is
being called. The router picks the model; this module just dispatches.
"""

from dataclasses import dataclass
from typing import Any

import instructor
import structlog
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config.settings import get_settings
from app.llm.router import ModelChoice
from app.llm.schemas import EventAnalysis

logger = structlog.get_logger(__name__)

# Module-level singleton clients — keep TCP connection pools across calls.
_openai_client: instructor.Instructor | None = None
_anthropic_client: instructor.Instructor | None = None


def _openai() -> instructor.Instructor:
    global _openai_client
    if _openai_client is None:
        key = get_settings().openai_api_key
        if not key:
            raise RuntimeError("OPENAI_API_KEY not configured")
        _openai_client = instructor.from_openai(AsyncOpenAI(api_key=key))
    return _openai_client


def _anthropic() -> instructor.Instructor:
    global _anthropic_client
    if _anthropic_client is None:
        key = get_settings().anthropic_api_key
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")
        _anthropic_client = instructor.from_anthropic(AsyncAnthropic(api_key=key))
    return _anthropic_client


@dataclass(frozen=True, slots=True)
class LLMCallResult:
    """What we get back from the LLM, after instructor validation."""

    analysis: EventAnalysis
    prompt_tokens: int
    completion_tokens: int


async def analyze_event(
    choice: ModelChoice,
    prompt: str,
) -> LLMCallResult:
    """Send `prompt` to the chosen model, return parsed EventAnalysis + token usage.

    Both providers expose `usage.prompt_tokens` / `usage.completion_tokens` on
    the raw response. instructor's `create_with_completion` returns both the
    parsed Pydantic object and the underlying raw response so we can capture
    cost data.
    """
    log = logger.bind(provider=choice.provider, model=choice.model)
    log.info("llm.call.started")

    if choice.provider == "openai":
        analysis, raw = await _openai().chat.completions.create_with_completion(
            model=choice.model,
            response_model=EventAnalysis,
            messages=[{"role": "user", "content": prompt}],
            max_retries=2,  # instructor re-prompts on validation failure
        )
        usage = raw.usage
        prompt_tokens = usage.prompt_tokens
        completion_tokens = usage.completion_tokens
    else:  # anthropic
        analysis, raw = await _anthropic().messages.create_with_completion(
            model=choice.model,
            response_model=EventAnalysis,
            messages=[{"role": "user", "content": prompt}],
            # Anthropic SDK requires explicit max_tokens. The schema allows an
            # 800-char summary + several impacts with up-to-2000-char reasoning
            # each — 1024 guaranteed truncation + instructor retry loops.
            max_tokens=4096,
            max_retries=2,
        )
        usage = raw.usage
        prompt_tokens = usage.input_tokens
        completion_tokens = usage.output_tokens

    log.info(
        "llm.call.completed",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        impacts=len(analysis.impacts),
    )
    return LLMCallResult(
        analysis=analysis,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def reset_clients_for_test() -> None:
    """Clear cached singletons — call from tests that monkeypatch the SDK or env."""
    global _openai_client, _anthropic_client
    _openai_client = None
    _anthropic_client = None


def build_prompt_v1(event_payload: dict[str, Any], watchlist: list[str]) -> str:
    """Render the v1 prompt — single event payload + watchlist. No macro context."""
    import json as _json
    from pathlib import Path

    template_path = Path(__file__).parent.parent / "prompts" / "event_analysis_v1.txt"
    template = template_path.read_text(encoding="utf-8")
    return template.format(
        event_json=_json.dumps(event_payload, indent=2, default=str),
        watchlist_csv=", ".join(watchlist),
    )


# Back-compat alias — existing call sites in tests / older code use `build_prompt`.
build_prompt = build_prompt_v1


def build_prompt_v2(ctx: "AnalyzerContext") -> str:  # noqa: F821 — forward ref
    """Render the v2 prompt — triggering event + macro indicators + recent events
    + attached documents (Phase B).

    `ctx` is `app.services.context_builder.AnalyzerContext`; the import is
    deferred to avoid a circular import (context_builder reads ORM models that
    indirectly route back through services).
    """
    import json as _json
    from pathlib import Path

    template_path = Path(__file__).parent.parent / "prompts" / "event_analysis_v2.txt"
    template = template_path.read_text(encoding="utf-8")
    return template.format(
        lookback_days=ctx.lookback_days,
        event_json=_json.dumps(ctx.triggering_event.payload, indent=2, default=str),
        indicators_table=_render_indicators_table(ctx.latest_indicators),
        recent_events_table=_render_recent_events_table(ctx.recent_events),
        attached_documents=_render_attached_documents(ctx.attached_documents),
        watchlist_csv=", ".join(ctx.watchlist),
    )


def build_prompt_v3(ctx: "AnalyzerContext") -> str:  # noqa: F821 — forward ref
    """Render the v3 prompt — v2 plus market state, self track record,
    per-window directions, and explicit scoring rules."""
    import json as _json
    from pathlib import Path

    template_path = Path(__file__).parent.parent / "prompts" / "event_analysis_v3.txt"
    template = template_path.read_text(encoding="utf-8")
    return template.format(
        lookback_days=ctx.lookback_days,
        event_json=_json.dumps(ctx.triggering_event.payload, indent=2, default=str),
        indicators_table=_render_indicators_table(ctx.latest_indicators),
        market_state_table=_render_market_state_table(ctx.market_state),
        track_record_table=_render_track_record_table(ctx.track_record),
        recent_events_table=_render_recent_events_table(ctx.recent_events),
        attached_documents=_render_attached_documents(ctx.attached_documents),
        watchlist_csv=", ".join(ctx.watchlist),
    )


def _fmt_pct(value: float | None) -> str:
    return f"{value:+.2%}" if value is not None else "n/a"


def _render_market_state_table(rows: list[Any]) -> str:
    """One line per ticker: trailing returns + annualized 20d realized vol."""
    if not rows:
        return "(no price history available)"
    lines = ["TICKER | 1D | 5D | 20D | 20D VOL (ann.)"]
    for r in rows:
        vol = f"{r.vol_20d_annualized:.1%}" if r.vol_20d_annualized is not None else "n/a"
        lines.append(
            f"{r.ticker} | {_fmt_pct(r.return_1d)} | {_fmt_pct(r.return_5d)} | "
            f"{_fmt_pct(r.return_20d)} | {vol}"
        )
    return "\n".join(lines)


def _render_track_record_table(rows: list[Any]) -> str:
    """Aggregate hit rates per (window, kind, direction). Small-n noted."""
    if not rows:
        return "(no validated history yet — calibrate from base rates alone)"
    lines = ["WINDOW | KIND | DIRECTION | ALIGNED/TOTAL | RATE"]
    for r in rows:
        window = r.window.value if hasattr(r.window, "value") else str(r.window)
        kind = r.kind.value if hasattr(r.kind, "value") else str(r.kind)
        direction = r.direction.value if hasattr(r.direction, "value") else str(r.direction)
        rate = f"{r.aligned / r.total:.0%}" if r.total else "n/a"
        note = " (small n)" if r.total < 5 else ""
        lines.append(
            f"{window} | {kind} | {direction} | {r.aligned}/{r.total} | {rate}{note}"
        )
    return "\n".join(lines)


def _render_indicators_table(snapshots: dict[str, Any]) -> str:
    """Compact one-line-per-indicator table: KEY | value | (Δ30d sign value)."""
    if not snapshots:
        return "(no indicators available)"
    lines = ["KEY | VALUE | 30-DAY CHANGE"]
    for key in sorted(snapshots):
        s = snapshots[key]
        if s.delta_30d is None:
            delta = "n/a"
        else:
            sign = "+" if s.delta_30d >= 0 else ""
            delta = f"{sign}{s.delta_30d:.3f}"
        lines.append(f"{key} | {s.value:.4f} | {delta}")
    return "\n".join(lines)


# Cap per-event body excerpt in the recent-events table so a single chatty
# FOMC statement doesn't dominate the lookback section. Real Fed statements
# run 2-3 KB; 400 chars is enough to read the key sentence + tail.
_RECENT_EVENT_BODY_CHARS = 400


def _recent_event_highlight(event: Any) -> str:
    """One-line highlight per event type — pulled out of the payload so the
    LLM sees more than the bare title.

    Adding a new event_type without a case here yields an empty highlight
    (the title alone still renders) — graceful degrade.
    """
    p = event.payload if isinstance(event.payload, dict) else {}
    et = event.event_type

    if et in ("CPI_RELEASE", "NFP_RELEASE", "GDP_RELEASE"):
        # Post-release-anchoring payloads carry a precomputed headline
        # ("MoM +0.30%, YoY +3.20%"); legacy payloads fall back to the level.
        headline = p.get("headline")
        v = p.get("value")
        label = {
            "CPI_RELEASE": "CPI",
            "NFP_RELEASE": "NFP",
            "GDP_RELEASE": "GDP",
        }[et]
        if headline:
            return f"{label} {headline} (level={v})"
        return f"{label} level={v}" if v is not None else ""
    if et == "FOMC_STATEMENT":
        # Phase C body is the actual Fed press release text; truncate.
        body = p.get("body") or p.get("description") or ""
        body_one_line = " ".join(body.split())
        return body_one_line[:_RECENT_EVENT_BODY_CHARS]
    if et == "DOT_PLOT_RELEASE":
        median = p.get("fed_funds_rate", {}).get("median", {})
        if median:
            parts = [f"{yr}={v}" for yr, v in median.items()]
            return "fed funds rate median — " + ", ".join(parts)
        return ""
    if et == "8K_FILING":
        ticker = p.get("ticker", "")
        items = p.get("item_codes", "")
        return f"{ticker} 8-K items={items}" if items else ""
    if et == "EARNINGS_REPORT":
        ticker = p.get("ticker", "")
        surprise = p.get("surprise_percent")
        f = p.get("fundamentals") or {}
        rev = f.get("revenue")
        rev_yoy = f.get("revenue_yoy_pct")
        parts = []
        if surprise is not None:
            parts.append(f"EPS surprise {surprise:+.2f}%")
        if rev is not None:
            parts.append(f"Revenue ${rev / 1e9:.1f}B")
        if rev_yoy is not None:
            parts.append(f"Rev YoY {rev_yoy:+.1f}%")
        return f"{ticker}: " + ", ".join(parts) if parts else ""
    return ""


# When inlining a prior prediction's reasoning into the prompt, truncate to
# keep the recent-events section bounded. Per-prediction storage is
# unaffected (DB still has the full text).
_PRIOR_REASONING_INLINE_CHARS = 250


def _render_prior_prediction(p: Any) -> str:
    """One-line-per-prediction summary including reasoning excerpt + outcomes."""
    kind_str = p.kind.value if hasattr(p.kind, "value") else str(p.kind)
    direction_str = p.direction.value if hasattr(p.direction, "value") else str(p.direction)
    magnitude_str = p.magnitude.value if hasattr(p.magnitude, "value") else str(p.magnitude)
    reasoning = p.reasoning[:_PRIOR_REASONING_INLINE_CHARS]
    if len(p.reasoning) > _PRIOR_REASONING_INLINE_CHARS:
        reasoning += "…"
    line = (
        f"    • {p.ticker} {kind_str} {direction_str} {magnitude_str} "
        f"conf={p.confidence:.2f} [{p.prompt_version}]"
    )
    if p.outcomes:
        outcomes_str = ", ".join(
            f"{o.window.value if hasattr(o.window, 'value') else o.window}: "
            f"excess={o.excess_return:+.2%} aligned={'✓' if o.aligned else '✗'}"
            for o in p.outcomes
        )
        line += f"\n      outcomes: {outcomes_str}"
    line += f'\n      reasoning: "{reasoning}"'
    return line


def _render_recent_events_table(events: list[Any]) -> str:
    """Multi-line block per recent event: header + highlight + prior predictions + outcomes."""
    if not events:
        return "(no recent events in window)"
    blocks: list[str] = []
    for e in events:
        lines = [
            f"[{e.published_at.date().isoformat()} | {e.source} | {e.event_type}] {e.title}"
        ]
        highlight = _recent_event_highlight(e)
        if highlight:
            lines.append(f"  {highlight}")
        if getattr(e, "prior_predictions", None):
            lines.append("  prior EventSense predictions:")
            for p in e.prior_predictions:
                lines.append(_render_prior_prediction(p))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _render_attached_documents(docs: list[Any]) -> str:
    """Render attached documents block — kind header + content per doc.

    docs are AttachedDocument dataclasses (content_text already truncated to
    the per-doc cap by context_builder).
    """
    if not docs:
        return "(no attached documents)"
    parts: list[str] = []
    for d in docs:
        kind = d.doc_kind.value if hasattr(d.doc_kind, "value") else str(d.doc_kind)
        parts.append(f"=== {kind} (source: {d.raw_url}) ===\n{d.content_text}")
    return "\n\n".join(parts)


# Latest prompt template version. The analyzer stamps the *configured*
# settings.analyzer_prompt_version onto each prediction row (so A/B across
# versions stays honest); this constant just names the current default.
PROMPT_VERSION = "v3"
