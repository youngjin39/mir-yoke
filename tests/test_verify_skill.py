"""Contract for the request-level completion matrix in the verify skill."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "mir-core" / "skills" / "verify" / "SKILL.md"


def test_verify_skill_requires_a_claim_per_target_and_item_and_an_n_of_m_report() -> None:
    workflow = SKILL.read_text(encoding="utf-8").split("## Workflow", 1)[1]
    assert "one claim per target × item" in workflow
    assert "otherwise report `N/M` with the open claims" in workflow
    assert "Finish every claim an agent can finish" in workflow
    assert "owner-only decisions, each with a recommendation, after the rest" in workflow
