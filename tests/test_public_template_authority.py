from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from e02a_binary import binary
from installed_mir import installed_mir as installed_mir
from installed_mir import run_installed_mir

ROOT = Path(__file__).resolve().parents[1]


# @spec CR-003 FR-006 IR-002 QR-002
def test_should_make_zero_writes_when_existing_repository_contract_is_missing(
    tmp_path, installed_mir
) -> None:
    before = sorted(tmp_path.rglob("*"))
    result = run_installed_mir(
        installed_mir, tmp_path, "bootstrap-adoption", "--project-root", str(tmp_path),
        "--json", "--apply",
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stderr == b""
    report = json.loads(result.stdout)
    assert report["changed_paths"] == []
    assert sorted(tmp_path.rglob("*")) == before


# @spec CR-003 IR-002
def test_should_expose_only_single_root_explicit_apply_mutation_flags() -> None:
    bootstrap = __import__("mir.cli.bootstrap", fromlist=["_parse"])
    adoption = __import__("mir.cli.bootstrap_adoption", fromlist=["_parse"])
    capability = __import__("mir.cli.capability", fromlist=["_parser"])

    assert bootstrap._parse(["--profile", "code_app"]).project_root is not None
    assert adoption._parse([]).apply is False
    parsed = capability._parser().parse_args(["sync"])
    assert parsed.apply is False
    assert parsed.project_root is not None


# @spec CR-003 QR-004
def test_should_never_infer_authority_from_a_local_catalog() -> None:
    hook = (ROOT / ".claude/hooks/pre-commit-verification.sh").read_text(
        encoding="utf-8"
    )

    assert "_MIR_FLEET_MANAGER" not in hook
    assert "repo-agent-management.json" not in hook


def test_product_commit_gate_recognizes_adopter_paths_and_commands() -> None:
    hook = (ROOT / ".claude/hooks/pre-commit-verification.sh").read_text(
        encoding="utf-8"
    )

    assert "apps/*" in hook
    assert "packages/*" in hook
    assert "npm run test --if-present" in hook
    assert "npm run typecheck --if-present" in hook
    assert "test_mir_mcp_server_live.py" not in hook


def test_should_require_tdd_evidence_when_adopter_product_roots_change(
    tmp_path: Path,
) -> None:
    guard = binary("project-hooks", "W5_PROJECT_HOOKS_BINARY")

    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "tdd.json").write_text(
        json.dumps({"version": 1, "changes": []}), encoding="utf-8"
    )
    changed = tmp_path / "changed-files.txt"
    shell_guard = (ROOT / ".claude/hooks/tdd-guard.sh").read_text(encoding="utf-8")

    for product_path in ("apps/web/main.ts", "packages/core/index.ts"):
        changed.write_text(product_path + "\n", encoding="utf-8")
        result = subprocess.run(
            [guard, "tdd-matrix", "precommit", str(tmp_path), str(changed)],
            cwd=tmp_path, env=dict(os.environ, HOME=str(tmp_path)),
            capture_output=True, timeout=15,
        )
        assert result.returncode == 2
        assert result.stdout == b""
        assert result.stderr == (
            "[PreCommitVerification BLOCK] No composite TDD entry found in "
            f"tasks/tdd.json for {product_path}.\n"
        ).encode()

    assert "apps/*" in shell_guard
    assert "packages/*" in shell_guard
