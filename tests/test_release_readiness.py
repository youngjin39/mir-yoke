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
        "test_installed_cli.py",
        "tools/mir_executor/tests/test_policy.py",
        "verify_codex_sync.py",
        "verify_project_agent_kit_evidence.py",
        "test_no_korean_in_user_facing.py",
        "pytest",
        "ruff",
    ):
        assert token in body


def test_tag_workflow_publishes_release_after_repository_validation() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "contents: write" in workflow
    assert "group: release-${{ github.ref }}" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "verify_release_readiness.py --current-clean-tree" in workflow
    assert "--require-project-agent-kit-evidence" not in workflow
    assert "git push" not in workflow
    assert workflow.index("verify_release_readiness.py") < workflow.index("gh release create")
    for token in (
        "gh release view",
        "gh release create",
        "--verify-tag",
        "--generate-notes",
        "startsWith(github.ref, 'refs/tags/v')",
    ):
        assert token in workflow
