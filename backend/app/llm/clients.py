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
            max_tokens=1024,  # anthropic SDK requires explicit max_tokens
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
    """Render the v2 prompt — triggering event + macro indicators + recent events.

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
        watchlist_csv=", ".join(ctx.watchlist),
    )


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


def _render_recent_events_table(events: list[Any]) -> str:
    """Compact one-line-per-event table: timestamp | source | event_type | title."""
    if not events:
        return "(no recent events in window)"
    lines = ["WHEN | SOURCE | TYPE | TITLE"]
    for e in events:
        lines.append(
            f"{e.published_at.date().isoformat()} | {e.source} | {e.event_type} | {e.title}"
        )
    return "\n".join(lines)


# The analyzer reads settings.analyzer_prompt_version to pick the template;
# this constant goes into the predictions.prompt_version column so we can A/B
# v1 vs v2 historical predictions in the accuracy endpoint.
PROMPT_VERSION = "v2"
