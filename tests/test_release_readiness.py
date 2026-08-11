from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# @spec FR-007 IR-001
def test_should_include_every_required_gate_when_release_script_is_inspected() -> None:
    script = ROOT / "scripts/verify_release_readiness.py"
    tree = ast.parse(script.read_text(encoding="utf-8"))
    body = script.read_text(encoding="utf-8")

    assert tree is not None
    assert '"clone"' in body
    assert '"--no-hardlinks"' in body
    assert '"--extra"' in body
    assert '"dev"' in body
    assert '["git", "init"' not in body
    for token in (
        "test_project_agent_kit.py",
        "test_project_agent_kit_release_evidence.py",
        "test_minimal_starter.py",
        "test_public_template_identity.py",
        "test_template_asset_classification.py",
        "test_decision_authority.py",
        "test_plugin_skill_packages.py",
        "test_common_skill_contracts.py",
        "test_capability_security.py",
        "verify_codex_sync.py",
        "verify_project_agent_kit_evidence.py",
        "test_no_korean_in_user_facing.py",
        "pytest",
        "ruff",
    ):
        assert token in body


def test_tag_workflow_requires_actual_project_agent_kit_evidence() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "--require-project-agent-kit-evidence" in workflow
