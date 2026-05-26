"""Unit tests for LLM cost calculation."""

import pytest

from app.llm.cost import estimate_cost_usd


def test_estimate_cost_gpt_4o_mini() -> None:
    # 1M input + 1M output tokens of gpt-4o-mini = $0.15 + $0.60 = $0.75
    cost = estimate_cost_usd("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == pytest.approx(0.75)


def test_estimate_cost_gpt_4o() -> None:
    # 500 input + 300 output tokens of gpt-4o
    # = 500 * 2.50 / 1M  +  300 * 10 / 1M
    # = 0.00125 + 0.003 = 0.00425
    cost = estimate_cost_usd("gpt-4o", prompt_tokens=500, completion_tokens=300)
    assert cost == pytest.approx(0.00425)


def test_estimate_cost_unknown_model_returns_zero() -> None:
    """Unknown model name = 0 cost (safe default; warning logged)."""
    cost = estimate_cost_usd("gpt-7-thinking", prompt_tokens=1000, completion_tokens=1000)
    assert cost == 0.0


def test_estimate_cost_case_insensitive_model() -> None:
    """Pricing lookup must be case-insensitive — SDK sometimes returns mixed case."""
    cost_lower = estimate_cost_usd("gpt-4o-mini", 500, 300)
    cost_upper = estimate_cost_usd("GPT-4o-Mini", 500, 300)
    assert cost_lower == cost_upper > 0
