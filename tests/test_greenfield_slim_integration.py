from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from mir.cli import bootstrap as bootstrap_cli
from mir.core.adoption.boundary import load_boundary, load_profile, payload_findings
from mir.core.adoption.slim import apply_adopter_slim
from scripts.verify_release_readiness import _materialize_candidate

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "profile",
    ("code_app", "hybrid_pipeline", "infra_runtime", "content_workspace"),
)
def test_should_compile_external_catalog_for_each_adopter_profile(
    tmp_path: Path, profile: str
) -> None:
    candidate = tmp_path / profile
    _materialize_candidate(ROOT, candidate)

    assert bootstrap_cli._compile_adopter_agent_catalog(candidate, profile) == [
        "config/repo-agent-management.json"
    ]

    catalog = json.loads(
        (candidate / "config/repo-agent-management.json").read_text(encoding="utf-8")
    )
    capabilities = json.loads(
        (candidate / "config/capability-sources.json").read_text(encoding="utf-8")
    )
    selected = capabilities["profiles"]["packs"][profile]
    assert set(catalog["templates"]) == {profile}
    assert set(catalog["catalog"]["agents"]) == {
        Path(path).stem for path in selected["agents"]
    }
    assert "template-sync-validator" not in catalog["catalog"]["agents"]
    assert all(
        metadata["status"] == "external" and metadata["source_path"] == "external"
        for metadata in catalog["catalog"]["skills"].values()
    )
    tracked_paths = catalog["templates"][profile]["tracked_paths"]
    assert all(
        not path.startswith("plugins/")
        for paths in tracked_paths.values()
        for path in paths
    )
    assert "config/capability-sources.json" in tracked_paths["harness_structure"]
    assert ".mir/capability-lock.json" in tracked_paths["harness_structure"]


def test_should_leave_only_runnable_adopter_payload_when_release_candidate_is_slimmed(
    tmp_path: Path,
    capsys,
) -> None:
    candidate = tmp_path / "candidate"
    _materialize_candidate(ROOT, candidate)

    assert (
        bootstrap_cli.main(
            [
                "--project-root",
                str(candidate),
                "--slug",
                "sample-product",
                "--profile",
                "code_app",
                "--purpose",
                "Build a deterministic sample product.",
                "--stack",
                "typescript",
                "--skip-capability-activation",
                "--allow-incomplete",
                "--json",
            ]
        )
        == 0
    )
    phase1 = json.loads(capsys.readouterr().out)
    assert phase1["status"] == "incomplete"
    profile = load_profile(candidate)
    assert profile["repo"]["repository_type"] == "code_app"
    assert "Mir Yoke — Harness Template Contract" not in (
        candidate / "CLAUDE.md"
    ).read_text(encoding="utf-8")
    catalog = json.loads(
        (candidate / "config/repo-agent-management.json").read_text(encoding="utf-8")
    )
    assert set(catalog["templates"]) == {"code_app"}
    assert all(
        metadata["status"] == "external" and metadata["source_path"] == "external"
        for metadata in catalog["catalog"]["skills"].values()
    )

    external_cli = tmp_path / "external-mir"
    external_cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    external_cli.chmod(0o755)
    report = apply_adopter_slim(
        candidate,
        external_cli=external_cli,
        verify=lambda _cli, _root: (True, "ready"),
    )

    assert report["status"] == "applied"
    assert payload_findings(
        candidate,
        boundary=load_boundary(candidate),
        profile=load_profile(candidate),
    ) == []
    assert not (candidate / "src/mir").exists()
    assert not (candidate / "plugins/mir-core").exists()
    assert not (candidate / "tools/harness_consistency").exists()
    assert not (candidate / "tests/test_adopter_slim.py").exists()
    assert (candidate / "scripts/mir.sh").is_file()
    assert not (candidate / ".mir/cli-runtime-lock.json").exists()
    assert (candidate / "config/cli-runtime-constraints.txt").is_file()
    assert not (candidate / ".claude/agents/template-sync-validator.md").exists()
    assert not (candidate / ".codex/agents/template-sync-validator.toml").exists()
    assert (candidate / "tasks/plan.md").read_text(encoding="utf-8") == (
        "# Plan\n\nNo active work.\n"
    )

    for script in (
        "scripts/verify_codex_sync.py",
        "scripts/verify_repo_agent_management.py",
    ):
        completed = subprocess.run(
            [sys.executable, script],
            cwd=candidate,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr

    tool_contract = subprocess.run(
        [sys.executable, "tools/hooks/validate_tool_contract.py"],
        cwd=candidate,
        input=json.dumps({"tool_name": "Bash", "tool_input": {}}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert tool_contract.returncode == 2
    assert "requires _mir_contract" in tool_contract.stderr
    assert "ModuleNotFoundError" not in tool_contract.stderr
