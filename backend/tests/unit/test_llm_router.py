"""Unit tests for the LLM model router — pure function, no LLM calls."""

import pytest

from app.db.models import EventSource
from app.llm.router import choose_model


@pytest.fixture(autouse=True)
def _llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_DAILY_COST_CAP_USD", "1.0")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_PREMIUM_MODEL", "gpt-4o")
    from app.config.settings import get_settings

    get_settings.cache_clear()


def test_high_stakes_event_under_budget_gets_premium_model() -> None:
    choice = choose_model(EventSource.FOMC, "FOMC_STATEMENT", today_spend_usd=0.05)
    assert choice.model == "gpt-4o"
    assert choice.provider == "openai"


def test_routine_event_under_budget_gets_default_model() -> None:
    choice = choose_model(EventSource.SEC_EDGAR, "8K_FILING", today_spend_usd=0.05)
    assert choice.model == "gpt-4o-mini"
    assert choice.provider == "openai"


def test_over_budget_downgrades_premium_to_default() -> None:
    # FOMC would normally get premium, but we're already at the cap.
    choice = choose_model(EventSource.FOMC, "FOMC_STATEMENT", today_spend_usd=1.5)
    assert choice.model == "gpt-4o-mini"


def test_provider_inferred_from_model_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "claude-3-5-haiku-latest")
    from app.config.settings import get_settings

    get_settings.cache_clear()
    choice = choose_model(EventSource.SEC_EDGAR, "8K_FILING", today_spend_usd=0.0)
    assert choice.provider == "anthropic"
    assert choice.model == "claude-3-5-haiku-latest"


def test_cpi_release_is_high_stakes() -> None:
    """CPI is in the high-stakes set per spec — should escalate to premium."""
    choice = choose_model(EventSource.FRED, "ECONOMIC_RELEASE", today_spend_usd=0.0)
    assert choice.model == "gpt-4o"


def test_earnings_is_not_high_stakes_by_default() -> None:
    """Earnings reports get the default model — common enough that premium would burn budget."""
    choice = choose_model(EventSource.EARNINGS, "EARNINGS_REPORT", today_spend_usd=0.0)
    assert choice.model == "gpt-4o-mini"
