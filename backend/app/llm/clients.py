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


def build_prompt(event_payload: dict[str, Any], watchlist: list[str]) -> str:
    """Render the v1 prompt template with this event's data + watchlist."""
    import json as _json  # local import to keep top imports clean
    from pathlib import Path

    template_path = Path(__file__).parent.parent / "prompts" / "event_analysis_v1.txt"
    template = template_path.read_text(encoding="utf-8")
    return template.format(
        event_json=_json.dumps(event_payload, indent=2, default=str),
        watchlist_csv=", ".join(watchlist),
    )


PROMPT_VERSION = "v1"
