"""Prove ADR-83 static readiness from a clean candidate Git tree."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = (
    (
        "focused-contracts",
        (
            "uv",
            "run",
            "pytest",
            "-q",
            "tests/test_project_agent_kit.py",
            "tests/test_project_agent_kit_release_evidence.py",
            "tests/test_minimal_starter.py",
            "tests/test_public_template_identity.py",
            "tests/test_template_asset_classification.py",
            "tests/test_decision_authority.py",
            "tests/test_public_template_surface.py",
            "tests/test_plugin_skill_packages.py",
            "tests/test_common_skill_contracts.py",
            "tests/test_capability_security.py",
        ),
    ),
    (
        "public-cli",
        (
            "uv",
            "run",
            "pytest",
            "-q",
            "tests/test_installed_cli.py",
            "tools/mir_executor/tests/test_policy.py",
        ),
    ),
    ("asset-classification", ("uv", "run", "python", "-m", "tools.template_assets", "--json")),
    ("derivatives", ("uv", "run", "python", "scripts/verify_codex_sync.py")),
    ("sanitization", ("uv", "run", "python", "tests/test_no_korean_in_user_facing.py")),
    ("links", ("uv", "run", "python", "tests/test_link_integrity.py")),
    ("schemas", ("uv", "run", "python", "tests/test_schema_validity.py")),
    ("full-tests", ("uv", "run", "pytest", "-q")),
    ("lint", ("uv", "run", "ruff", "check")),
)
EVIDENCE_CHECK = (
    "project-agent-kit-clean-room-evidence",
    ("uv", "run", "python", "scripts/verify_project_agent_kit_evidence.py"),
)


def _candidate_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(path for path in result.stdout.splitlines() if path and (root / path).is_file())


def _materialize_candidate(source: Path, target: Path) -> None:
    subprocess.run(
        ["git", "clone", "-q", "--no-hardlinks", str(source), str(target)],
        check=True,
    )
    desired = set(_candidate_paths(source))
    cloned = set(_candidate_paths(target))
    for relative in sorted(cloned - desired):
        target_path = target / relative
        if target_path.is_file() or target_path.is_symlink():
            target_path.unlink()
            parent = target_path.parent
            while parent != target:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
    for relative in sorted(desired):
        source_path = source / relative
        target_path = target / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_symlink():
            target_path.symlink_to(source_path.readlink())
        else:
            shutil.copy2(source_path, target_path)
    subprocess.run(["git", "add", "-A"], cwd=target, check=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Mir Yoke Readiness",
        "GIT_AUTHOR_EMAIL": "readiness@invalid",
        "GIT_COMMITTER_NAME": "Mir Yoke Readiness",
        "GIT_COMMITTER_EMAIL": "readiness@invalid",
    }
    changed = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=target).returncode
    if changed:
        subprocess.run(
            ["git", "commit", "-q", "-m", "temporary release candidate"],
            cwd=target,
            check=True,
            env=env,
        )


def run_checks(
    root: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    *,
    require_evidence: bool = False,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    checks = CHECKS + ((EVIDENCE_CHECK,) if require_evidence else ())
    for name, command in checks:
        completed = runner(command, cwd=root, check=False, text=True)
        results.append({"name": name, "command": list(command), "exit_code": completed.returncode})
        if completed.returncode != 0:
            break
    return results


def _verify_clean_tree(root: Path) -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        raise RuntimeError("release verification requires a clean candidate Git tree")


# @spec CR-006 FR-007 IR-001
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_release_readiness.py")
    parser.add_argument("--current-clean-tree", action="store_true")
    parser.add_argument("--require-project-agent-kit-evidence", action="store_true")
    args = parser.parse_args(argv)

    if not args.current_clean_tree:
        with tempfile.TemporaryDirectory(prefix="mir-yoke-release-") as raw:
            candidate = Path(raw) / "candidate"
            _materialize_candidate(ROOT, candidate)
            command = [
                "uv",
                "run",
                "--extra",
                "dev",
                "python",
                "scripts/verify_release_readiness.py",
                "--current-clean-tree",
            ]
            if args.require_project_agent_kit_evidence:
                command.append("--require-project-agent-kit-evidence")
            return subprocess.run(command, cwd=candidate, check=False).returncode

    try:
        _verify_clean_tree(ROOT)
        results = run_checks(ROOT, require_evidence=args.require_project_agent_kit_evidence)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"release readiness: ERROR: {exc}", file=sys.stderr)
        return 1
    expected_count = len(CHECKS) + int(args.require_project_agent_kit_evidence)
    ready = len(results) == expected_count and all(row["exit_code"] == 0 for row in results)
    print(json.dumps({"ready": ready, "checks": results}, indent=2))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
