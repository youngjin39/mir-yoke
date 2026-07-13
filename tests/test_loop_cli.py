from pathlib import Path

from mir.cli.loop import next_step


def test_failed_step_returns_control_without_attempt_block(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text(
        "# Plan\n\n"
        "## Active Loop Cursor\n"
        "Step 1: FAILED | attempts=99 | brief=tasks/dispatch/one.md | tdd=one#unit\n",
        encoding="utf-8",
    )

    result = next_step(plan)

    assert result.status == "FAILED"
    assert result.reason == "operator_decision_required"
