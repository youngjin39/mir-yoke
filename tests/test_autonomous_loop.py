"""Regression tests for proportional autonomous-loop intervention signals."""

from tools.autonomous_loop.loop import (
    RETRY_BUDGET_THRESHOLD,
    trigger_circuit_breaker,
    trigger_external_side_effect,
    trigger_interrupt,
    trigger_retry_budget,
)


def test_retry_budget_is_observation_only() -> None:
    result = trigger_retry_budget(
        {"retry_count": {"total": RETRY_BUDGET_THRESHOLD}}
    )

    assert result is not None
    assert result.trigger_id == "retry_budget"
    assert result.should_request_approval is False


def test_circuit_breaker_still_requests_approval() -> None:
    result = trigger_circuit_breaker({"state": "open"})

    assert result is not None
    assert result.trigger_id == "circuit_breaker"
    assert result.should_request_approval is True


def test_interrupt_still_requests_approval(tmp_path) -> None:
    interrupt = tmp_path / "interrupt.flag"
    interrupt.touch()

    result = trigger_interrupt(interrupt)

    assert result is not None
    assert result.trigger_id == "interrupt"
    assert result.should_request_approval is True


def test_external_side_effect_still_requests_approval(tmp_path) -> None:
    policy = tmp_path / "external_side_effects.yaml"
    policy.write_text("always_require_approval:\n  - deploy\n", encoding="utf-8")

    result = trigger_external_side_effect("deploy", policy)

    assert result is not None
    assert result.trigger_id == "external_side_effect"
    assert result.should_request_approval is True
