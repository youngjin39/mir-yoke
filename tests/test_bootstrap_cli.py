from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tomllib
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest

from mir.cli import SUBCOMMANDS
from mir.cli import bootstrap as bootstrap_cli

_SOURCE_CONFIG = {
    "schema_version": 1,
    "source": {
        "url": "https://github.com/example/mir-yoke.git",
        "ref": "refs/heads/main",
    },
    "plugins": {"mir-core": {"path": "plugins/mir-core"}},
    "profiles": {
        "packs": {
            "code_app": ["mir-core"],
            "content_workspace": ["mir-core"],
        }
    },
}


def _write(path: Path, body: str = "placeholder\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _make_harness_surfaces(root: Path) -> None:
    _write(root / "CLAUDE.md")
    _write(root / "AGENTS.md")
    _write(root / ".claude" / "settings.json", '{"hooks":{"SessionStart":[]}}\n')
    _write(
        root / ".codex" / "config.toml",
        'approval_policy = "on-request"\nsandbox_mode = "workspace-write"\n',
    )
    _write(root / ".codex" / "hooks.json", "{}\n")
    _write(root / ".ai-harness" / "deny-list.yaml", "deny: []\n")
    _write(root / ".claude" / "agents" / "main-orchestrator.md")
    _write(root / ".codex" / "agents" / "main-orchestrator.toml")
    _write(root / ".claude" / "hooks" / "session-start.sh", "#!/usr/bin/env bash\n")
    _write(root / "config" / "sub-agent-policy.json", "{}\n")
    _write(
        root / "config" / "capability-sources.json",
        json.dumps(_SOURCE_CONFIG) + "\n",
    )
    _write(
        root / "config" / "adopter-boundary.json",
        json.dumps(
            {
                "schema_version": 1,
                "provider_owners": [
                    {
                        "slug": "mir-yoke",
                        "repository_types": ["public_harness_template"],
                    }
                ],
                "provider_markers": ["src/mir"],
                "provider_text_markers": [],
                "source_asset_manifest": "config/template-assets.json",
                "payload_manifest": "config/adopter-payload.json",
                "remove_classifications": ["template-maintainer-tool"],
            }
        )
        + "\n",
    )
    _write(
        root / "config" / "adopter-payload.json",
        json.dumps(
            {
                "schema_version": 1,
                "generated_from": "config/template-assets.json",
                "files": [],
            }
        )
        + "\n",
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)


def _bootstrap(root: Path, *extra: str) -> int:
    return bootstrap_cli.main(
        [
            "--project-root",
            str(root),
            "--slug",
            "sample-project",
            "--profile",
            "code_app",
            "--purpose",
            "Build and verify a portable sample project harness.",
            "--stack",
            "python,markdown",
            "--skip-capability-activation",
            "--allow-incomplete",
            "--json",
            *extra,
        ]
    )


# @spec FR-001 FR-004 QR-001
def test_should_return_unsupported_when_native_windows_bootstrap_would_mutate(
    tmp_path, capsys, monkeypatch
):
    marker = tmp_path / "existing.txt"
    marker.write_text("preserve me\n", encoding="utf-8")
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    monkeypatch.setattr(bootstrap_cli.platform, "system", lambda: "Windows")

    assert bootstrap_cli.main(["--project-root", str(tmp_path)]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Native Windows automated bootstrap is unsupported" in captured.err
    assert "setup.sh inside WSL" in captured.err
    assert "agent-guided existing-repository/reference adaptation" in captured.err
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before
    assert marker.read_text(encoding="utf-8") == "preserve me\n"


def test_should_allow_read_only_bootstrap_help_on_native_windows(capsys, monkeypatch):
    monkeypatch.setattr(bootstrap_cli.platform, "system", lambda: "Windows")

    with pytest.raises(SystemExit) as exc:
        bootstrap_cli.main(["--help"])

    assert exc.value.code == 0
    assert "usage: mir bootstrap" in capsys.readouterr().out


# @spec FR-001 FR-004 QR-001
def test_should_return_unsupported_before_mutation_on_other_unsupported_platforms(
    tmp_path, capsys, monkeypatch
):
    marker = tmp_path / "existing.txt"
    marker.write_text("preserve me\n", encoding="utf-8")
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    monkeypatch.setattr(bootstrap_cli.platform, "system", lambda: "FreeBSD")

    assert bootstrap_cli.main(["--project-root", str(tmp_path)]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "supports macOS, Linux, and WSL" in captured.err
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before
    assert marker.read_text(encoding="utf-8") == "preserve me\n"


def test_should_return_success_when_bootstrap_runs_inside_wsl_linux(
    tmp_path, capsys, monkeypatch
):
    _make_harness_surfaces(tmp_path)
    monkeypatch.setattr(bootstrap_cli.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        bootstrap_cli.platform,
        "release",
        lambda: "6.6.87.2-microsoft-standard-WSL2",
    )

    assert _bootstrap(tmp_path) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["platform"]["os"] == "linux"
    assert "microsoft-standard-WSL2" in report["platform"]["release"]


# @spec FR-001 FR-004 QR-002
def test_should_reject_provider_push_remote_before_bootstrap_mutation(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:example/mir-yoke.git"],
        cwd=tmp_path,
        check=True,
    )
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }

    assert _bootstrap(tmp_path) == 2

    captured = capsys.readouterr()
    assert "Git push remote still targets the Mir Yoke provider" in captured.err
    assert "git remote rename origin mir-yoke-upstream" in captured.err
    assert "git remote set-url --push mir-yoke-upstream DISABLED" in captured.err
    assert not (tmp_path / ".mir/bootstrap-receipt.json").exists()
    assert {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and ".git" not in path.parts
    } == before


def test_should_treat_default_git_ports_as_the_same_provider(tmp_path, capsys):
    for push_url in (
        "ssh://git@github.com:22/example/mir-yoke.git",
        "https://github.com:443/example/mir-yoke.git",
    ):
        project = tmp_path / sha256(push_url.encode()).hexdigest()[:8]
        _make_harness_surfaces(project)
        subprocess.run(["git", "remote", "add", "origin", push_url], cwd=project, check=True)

        assert _bootstrap(project) == 2
        assert "still targets the Mir Yoke provider" in capsys.readouterr().err


def test_source_control_receipt_never_persists_remote_credentials(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://product-user:secret-token@example.com/product/repository.git",
        ],
        cwd=tmp_path,
        check=True,
    )

    assert _bootstrap(tmp_path) == 0

    output = capsys.readouterr().out
    assert "secret-token" not in output
    receipt = json.loads(output)
    assert receipt["source_control"]["remotes"] == [
        {
            "name": "origin",
            "push_destinations": ["example.com/product/repository"],
        }
    ]


def test_should_fail_before_mutation_when_provider_source_is_unavailable(
    tmp_path, capsys
):
    for body in (None, "{invalid"):
        project = tmp_path / ("missing" if body is None else "invalid")
        _make_harness_surfaces(project)
        source = project / "config/capability-sources.json"
        if body is None:
            source.unlink()
        else:
            source.write_text(body, encoding="utf-8")
        before = {
            path.relative_to(project).as_posix(): path.read_bytes()
            for path in project.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }

        assert _bootstrap(project) == 2
        assert "Git ownership cannot be verified" in capsys.readouterr().err
        assert not (project / ".mir/bootstrap-receipt.json").exists()
        assert {
            path.relative_to(project).as_posix(): path.read_bytes()
            for path in project.rglob("*")
            if path.is_file() and ".git" not in path.parts
        } == before


def _write_architecture_evidence(root: Path, commit: str) -> None:
    _write(root / "spec" / "STATE.md", "# Project specification state\n\nAll requirements ready.\n")
    _write(
        root / "spec" / "index.yaml",
        "version: 1\nrequirements:\n  - id: REQ-001\n    status: ready\n",
    )
    _write(
        root / "spec" / "graph.yaml",
        "nodes:\n  - id: REQ-001\nedges: []\n",
    )
    _write(root / "spec" / "gaps.yaml", "gaps: []\n")
    _write(
        root / "spec" / "bootstrap-evidence.json",
        json.dumps(
            {
                "schema_version": 2,
                "sequence": ["mir-core:design", "mir-core:spec-architect"],
                "capability_commit": commit,
                "outputs": [
                    "spec/STATE.md",
                    "spec/index.yaml",
                    "spec/graph.yaml",
                    "spec/gaps.yaml",
                ],
                "coverage": {
                    "l1": {"total": 1, "filled": 1, "derived": 0, "na": 0, "tbd": 0},
                    "l2": {"total": 1, "filled": 1, "derived": 0, "na": 0, "tbd": 0},
                    "l3": {"total": 9, "filled": 9, "derived": 0, "na": 0, "tbd": 0},
                    "l4": {"total": 10, "filled": 10, "derived": 0, "na": 0, "tbd": 0},
                    "ai_ready": {"ready": 1, "incomplete": 0, "blocked": 0},
                },
                "open_gaps": 0,
                "full_review": {
                    "project_structure": "pass",
                    "memory": "pass",
                    "discoverability": "pass",
                    "requirements": "pass",
                    "organization": "pass",
                },
            }
        )
        + "\n",
    )
    _write(
        root / ".mir" / "capability-lock.json",
        json.dumps({"source": {"commit": commit}}) + "\n",
    )


def test_authored_baseline_rejects_a_symlinked_contract_directory(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / ".ai-harness").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="authored directory is unsafe"):
        bootstrap_cli._ensure_authored_files(
            tmp_path,
            "sample-product",
            "code_app",
            "Build a safe sample product.",
            ["typescript"],
            None,
            None,
        )

    assert list(outside.iterdir()) == []
    assert not (tmp_path / ".mir").exists()
    assert not (tmp_path / "docs").exists()
    assert not (tmp_path / "tasks").exists()


# @spec FR-001 FR-004
def test_bootstrap_builds_required_memory_and_is_idempotent(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)

    assert _bootstrap(tmp_path) == 0
    first_stdout = json.loads(capsys.readouterr().out)
    receipt_path = tmp_path / ".mir" / "bootstrap-receipt.json"
    first_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    first_projection = (tmp_path / "docs" / "memory-map.md").read_text(encoding="utf-8")

    assert first_stdout["status"] == "incomplete"
    assert first_receipt["capabilities"]["status"] == "skipped"
    assert first_receipt["memory"]["topology"] == "per_repository_sqlite_fts5"
    assert first_receipt["memory"]["archive_fts_probe"] == "ok"
    assert first_receipt["memory"]["archives_registered"] == 3
    assert (tmp_path / "harness_a.toml").is_file()
    assert (tmp_path / ".mir" / "memory.db").is_file()

    assert _bootstrap(tmp_path) == 0
    capsys.readouterr()
    second_projection = (tmp_path / "docs" / "memory-map.md").read_text(encoding="utf-8")
    assert second_projection == first_projection
    with sqlite3.connect(tmp_path / ".mir" / "memory.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM external_archives").fetchone()[0] == 3


def test_bootstrap_receipt_binds_isolated_cli_source_evidence(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    evidence = {
        "MIR_BOOTSTRAP_RUNTIME_ID": "runtime-123",
        "MIR_BOOTSTRAP_SOURCE_URL": "https://github.com/example/mir-yoke.git",
        "MIR_BOOTSTRAP_SOURCE_COMMIT": "a" * 40,
        "MIR_BOOTSTRAP_SOURCE_LOCK_SHA256": "b" * 64,
        "MIR_BOOTSTRAP_CONSTRAINTS_SHA256": "c" * 64,
        "MIR_BOOTSTRAP_RUNTIME_MANIFEST": "/external/runtime-manifest.json",
        "MIR_BOOTSTRAP_RUNTIME_MANIFEST_SHA256": "d" * 64,
    }

    with patch.dict(os.environ, evidence, clear=False):
        assert _bootstrap(tmp_path) == 0

    receipt = json.loads(capsys.readouterr().out)
    assert receipt["cli"] == {
        "executable": None,
        "sha256": None,
        "externalized": False,
        "runtime_id": "runtime-123",
        "source_url": "https://github.com/example/mir-yoke.git",
        "source_commit": "a" * 40,
        "source_lock_sha256": "b" * 64,
        "constraints_sha256": "c" * 64,
        "runtime_manifest": "/external/runtime-manifest.json",
        "runtime_manifest_sha256": "d" * 64,
    }
    assert receipt["source_control"]["status"] == "local_only"


def test_bootstrap_receipt_preserves_the_namespaced_launcher_symlink(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    runtime_root = tmp_path.parent / f"{tmp_path.name}-runtime"
    inner_cli = runtime_root / "tools/mir-harness/bin/mir"
    outer_cli = runtime_root / "bin/mir"
    inner_cli.parent.mkdir(parents=True)
    outer_cli.parent.mkdir(parents=True)
    inner_cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    inner_cli.chmod(0o755)
    outer_cli.symlink_to(inner_cli)
    evidence = {
        "MIR_BOOTSTRAP_CLI_PATH": str(outer_cli),
        "MIR_BOOTSTRAP_RUNTIME_ID": "runtime-123",
        "MIR_BOOTSTRAP_SOURCE_URL": "https://github.com/example/mir-yoke.git",
        "MIR_BOOTSTRAP_SOURCE_COMMIT": "a" * 40,
        "MIR_BOOTSTRAP_SOURCE_LOCK_SHA256": "b" * 64,
        "MIR_BOOTSTRAP_CONSTRAINTS_SHA256": "c" * 64,
        "MIR_BOOTSTRAP_RUNTIME_MANIFEST": str(runtime_root / "runtime-manifest.json"),
        "MIR_BOOTSTRAP_RUNTIME_MANIFEST_SHA256": "d" * 64,
    }

    with patch.dict(os.environ, evidence, clear=False):
        assert _bootstrap(tmp_path) == 0

    receipt = json.loads(capsys.readouterr().out)
    assert receipt["cli"]["executable"] == str(outer_cli)
    assert receipt["cli"]["sha256"] == sha256(inner_cli.read_bytes()).hexdigest()


def test_should_convert_exact_provider_profile_when_phase1_is_explicit(
    tmp_path, capsys
):
    _make_harness_surfaces(tmp_path)
    provider_plan = "# Mir Yoke maintainer plan\n"
    provider_contract = "# Mir Yoke — Harness Template Contract\n"
    _write(tmp_path / "tasks/plan.md", provider_plan)
    _write(tmp_path / "CLAUDE.md", provider_contract)
    payload_path = tmp_path / "config/adopter-payload.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["files"] = [
        {
            "path": "tasks/plan.md",
            "sha256": sha256(provider_plan.encode()).hexdigest(),
            "classification": "reference",
            "disposition": "remove",
        },
        {
            "path": "CLAUDE.md",
            "sha256": sha256(provider_contract.encode()).hexdigest(),
            "classification": "starter",
            "disposition": "preserve",
        },
    ]
    payload_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    _write(
        tmp_path / ".mir/repo-profile.toml",
        '[repo]\nslug = "mir-yoke"\nrepository_type = "public_harness_template"\n',
    )

    assert _bootstrap(tmp_path) == 0
    receipt = json.loads(capsys.readouterr().out)
    profile = tomllib.loads(
        (tmp_path / ".mir/repo-profile.toml").read_text(encoding="utf-8")
    )

    assert receipt["status"] == "incomplete"
    assert profile["repo"]["slug"] == "sample-project"
    assert profile["repo"]["repository_type"] == "code_app"
    assert profile["repo"]["overlay_archetype"] == "product_adopter"
    assert (tmp_path / "tasks/plan.md").read_text(encoding="utf-8") == (
        "# Plan\n\nNo active work.\n"
    )
    assert "Build and verify a portable sample project harness" in (
        tmp_path / "CLAUDE.md"
    ).read_text(encoding="utf-8")
    assert "Harness Template Contract" not in (tmp_path / "CLAUDE.md").read_text(
        encoding="utf-8"
    )
    assert not (tmp_path / ".mir/cli-runtime-lock.json").exists()


def test_content_workspace_classifies_existing_records_and_proves_search(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    _write(
        tmp_path / "career-records" / "applications.md",
        "# Applications\n\nAcmePlatform interview preparation and outcome notes.\n",
    )

    assert (
        bootstrap_cli.main(
            [
                "--project-root",
                str(tmp_path),
                "--slug",
                "career-harness",
                "--profile",
                "content_workspace",
                "--purpose",
                "Organize career transitions and application evidence.",
                "--stack",
                "markdown,sqlite",
                "--archive",
                "applications=career-records",
                "--skip-capability-activation",
                "--allow-incomplete",
                "--json",
            ]
        )
        == 0
    )

    receipt = json.loads(capsys.readouterr().out)
    manifest = json.loads(
        (tmp_path / "config" / "content-onboarding.json").read_text(encoding="utf-8")
    )
    assert receipt["content_onboarding"]["status"] == "pass"
    assert {item["classification"] for item in manifest["archives"]} == {
        "project-definition",
        "applications",
    }
    assert manifest["scan"]["unclassified"] == []
    assert manifest["archives"][1]["path"] == "career-records"
    assert manifest["archives"][1]["formats"] == ["md"]
    assert all(query["status"] == "pass" for query in receipt["content_onboarding"]["queries"])
    assert "Organize career transitions" in (
        tmp_path / "docs" / "project-purpose.md"
    ).read_text(encoding="utf-8")


def test_content_workspace_blocks_unclassified_existing_records(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    _write(tmp_path / "legacy-notes" / "history.md", "UniqueHistory evidence.\n")

    assert (
        bootstrap_cli.main(
            [
                "--project-root",
                str(tmp_path),
                "--profile",
                "content_workspace",
                "--purpose",
                "Organize historical records for reliable retrieval.",
                "--stack",
                "markdown",
                "--skip-capability-activation",
                "--allow-incomplete",
                "--json",
            ]
        )
        == 2
    )
    report = json.loads(capsys.readouterr().out)
    assert any("unclassified existing content" in error for error in report["errors"])
    assert not (tmp_path / "config" / "content-onboarding.json").exists()


def test_content_workspace_reports_non_indexable_record_formats(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    _write(tmp_path / "legacy-documents" / "resume.pdf", "%PDF sample\n")
    base = [
        "--project-root",
        str(tmp_path),
        "--profile",
        "content_workspace",
        "--purpose",
        "Organize historical application records for retrieval.",
        "--stack",
        "markdown",
        "--skip-capability-activation",
        "--allow-incomplete",
        "--json",
    ]

    assert bootstrap_cli.main(base) == 2
    discovery = json.loads(capsys.readouterr().out)
    assert any("legacy-documents [pdf]" in error for error in discovery["errors"])

    assert bootstrap_cli.main([*base, "--archive", "resumes=legacy-documents"]) == 2
    conversion = json.loads(capsys.readouterr().out)
    assert any("non-indexable formats ['pdf']" in error for error in conversion["errors"])
    assert any("UTF-8 text projection" in error for error in conversion["errors"])


def test_content_finalize_blocks_stale_onboarding_manifest(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    _write(
        tmp_path / "career-records" / "timeline.md",
        "StableCareerTimeline for the initial memory acceptance.\n",
    )
    phase1 = [
        "--project-root",
        str(tmp_path),
        "--slug",
        "career-harness",
        "--profile",
        "content_workspace",
        "--purpose",
        "Organize career transitions and application evidence.",
        "--stack",
        "markdown,sqlite",
        "--archive",
        "career-history=career-records",
        "--skip-capability-activation",
        "--allow-incomplete",
        "--json",
    ]
    assert bootstrap_cli.main(phase1) == 0
    capsys.readouterr()
    _write(
        tmp_path / "career-records" / "new-interview.md",
        "NewInterviewEvidence added after the onboarding receipt.\n",
    )

    assert (
        bootstrap_cli.main(
            [
                "--project-root",
                str(tmp_path),
                "--slug",
                "career-harness",
                "--profile",
                "content_workspace",
                "--finalize",
                "--skip-capability-activation",
                "--allow-incomplete",
                "--json",
            ]
        )
        == 2
    )
    report = json.loads(capsys.readouterr().out)
    assert any("content onboarding manifest is stale" in error for error in report["errors"])


def test_external_storage_root_is_verified_and_recorded(tmp_path, capsys):
    project = tmp_path / "project"
    storage = tmp_path / "machine-storage"
    project.mkdir()
    _make_harness_surfaces(project)
    runtime_id = "sample-runtime"
    expected = {
        "UV_CACHE_DIR": storage / "uv" / "cache",
        "UV_PYTHON_INSTALL_DIR": storage / "uv" / "python",
        "UV_TOOL_DIR": storage / "mir" / "cli" / runtime_id / "tools",
        "UV_TOOL_BIN_DIR": storage / "mir" / "cli" / runtime_id / "bin",
        "MIR_CAPABILITY_HOME": storage / "mir" / "capabilities",
    }
    for path in expected.values():
        path.mkdir(parents=True, exist_ok=True)

    storage_env = {name: str(path) for name, path in expected.items()}
    storage_env["MIR_BOOTSTRAP_RUNTIME_ID"] = runtime_id
    storage_env["UV_PROJECT_ENVIRONMENT"] = str(project / ".venv")
    with patch.dict(os.environ, storage_env):
        assert _bootstrap(project, "--storage-root", str(storage)) == 0

    receipt = json.loads(capsys.readouterr().out)
    assert receipt["storage"]["mode"] == "external-first"
    assert receipt["storage"]["root"] == str(storage.resolve())
    assert receipt["storage"]["same_filesystem_as_project"] is True
    assert receipt["storage"]["large_payloads"] == {
        name: str(path.resolve()) for name, path in expected.items()
    }


def test_external_storage_root_requires_wrapper_environment(tmp_path, capsys):
    project = tmp_path / "project"
    storage = tmp_path / "machine-storage"
    project.mkdir()
    storage.mkdir()
    _make_harness_surfaces(project)

    with patch.dict(
        os.environ,
        {
            "UV_CACHE_DIR": "",
            "UV_PYTHON_INSTALL_DIR": "",
            "UV_TOOL_DIR": "",
            "UV_TOOL_BIN_DIR": "",
            "MIR_CAPABILITY_HOME": "",
            "UV_PROJECT_ENVIRONMENT": "",
        },
    ):
        assert _bootstrap(project, "--storage-root", str(storage)) == 2

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "incomplete"
    assert report["storage"]["mode"] == "external-first"
    assert any("UV_CACHE_DIR" in error for error in report["errors"])
    assert not (project / ".mir" / "memory.db").exists()


def test_preflight_failure_does_not_create_authored_config_or_db(tmp_path, capsys):
    _write(tmp_path / "CLAUDE.md")
    _write(
        tmp_path / "config/capability-sources.json",
        json.dumps(_SOURCE_CONFIG) + "\n",
    )

    assert _bootstrap(tmp_path) == 1
    report = json.loads(capsys.readouterr().out)

    assert report["status"] == "incomplete"
    assert not (tmp_path / "harness_a.toml").exists()
    assert not (tmp_path / ".mir" / "memory.db").exists()
    assert (tmp_path / ".mir" / "bootstrap-receipt.json").is_file()


def test_bootstrap_requires_jq_for_active_hook_payloads(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    real_which = bootstrap_cli.shutil.which
    with patch.object(
        bootstrap_cli.shutil,
        "which",
        side_effect=lambda name: None if name == "jq" else real_which(name),
    ):
        assert _bootstrap(tmp_path) == 1

    report = json.loads(capsys.readouterr().out)
    assert report["platform"]["hook_runtime"]["jq"] == "missing"
    assert any("requires jq" in error for error in report["errors"])
    assert not (tmp_path / ".mir" / "memory.db").exists()


def test_invalid_existing_config_is_preserved_and_blocks_bootstrap(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    invalid = "[memory\nenabled = true\n"
    _write(tmp_path / "harness_a.toml", invalid)

    assert _bootstrap(tmp_path) == 2
    capsys.readouterr()

    assert (tmp_path / "harness_a.toml").read_text(encoding="utf-8") == invalid
    assert not (tmp_path / ".mir" / "memory.db").exists()


def test_existing_projection_text_outside_markers_is_preserved(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    _write(tmp_path / "docs" / "memory-map.md", "Authored introduction.\n")

    assert _bootstrap(tmp_path) == 0
    capsys.readouterr()

    rendered = (tmp_path / "docs" / "memory-map.md").read_text(encoding="utf-8")
    assert rendered.startswith("Authored introduction.\n")
    assert "<!-- mir:generated:start -->" in rendered
    assert "<!-- mir:generated:end -->" in rendered


def test_bootstrap_source_has_no_symlink_dependency():
    root = Path(__file__).resolve().parents[1]
    for relative in ("setup.sh", "setup.ps1", "src/mir/cli/bootstrap.py"):
        assert not (root / relative).is_symlink()


def test_legacy_cli_registry_is_importable_but_has_no_public_module_entrypoint() -> None:
    assert {"bootstrap", "capability"} <= set(SUBCOMMANDS)
    for command in ("bootstrap", "capability"):
        completed = subprocess.run(
            [sys.executable, "-m", "mir", command, "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 2
        assert "exposes no public CLI" in completed.stderr


def test_capability_install_requires_restart_before_ready(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    evidence = {
        "source_commit": "a" * 40,
        "selected_plugins": ["mir-core"],
        "selected_agents": ["main-orchestrator"],
    }

    with patch.object(bootstrap_cli, "_activate_capabilities", return_value=("ready", evidence)):
        assert (
            bootstrap_cli.main(
                [
                    "--project-root",
                    str(tmp_path),
                    "--profile",
                    "code_app",
                    "--purpose",
                    "Build a portable application harness.",
                    "--stack",
                    "python",
                    "--json",
                ]
            )
            == 0
        )
    install_receipt = json.loads(capsys.readouterr().out)
    assert install_receipt["status"] == "restart_required"
    assert install_receipt["capabilities"]["status"] == "restart_required"
    assert install_receipt["slim"]["status"] == "not_run"
    _write_architecture_evidence(tmp_path, "a" * 40)

    with (
        patch.object(bootstrap_cli, "_finalize_capabilities", return_value=("ready", evidence)),
        patch.object(
            bootstrap_cli,
            "apply_adopter_slim",
            return_value={"status": "already_slim", "removed": [], "preserved_modified": []},
        ),
    ):
        assert (
            bootstrap_cli.main(
                [
                    "--project-root",
                    str(tmp_path),
                    "--profile",
                    "code_app",
                    "--finalize",
                    "--architecture-initialized",
                    "--json",
                ]
            )
            == 0
        )
    final_receipt = json.loads(capsys.readouterr().out)
    assert final_receipt["status"] == "ready"
    assert final_receipt["slim"]["status"] == "already_slim"
    assert final_receipt["capabilities"]["selected_plugins"] == ["mir-core"]
    assert final_receipt["architecture_initialization"]["attested"] is True
    assert set(final_receipt["architecture_initialization"]["evidence"]["output_hashes"]) == {
        "spec/STATE.md",
        "spec/index.yaml",
        "spec/graph.yaml",
        "spec/gaps.yaml",
    }


def test_finalize_rolls_back_slim_when_ready_receipt_cannot_publish(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    evidence = {
        "source_commit": "a" * 40,
        "selected_plugins": ["mir-core"],
    }
    with patch.object(bootstrap_cli, "_activate_capabilities", return_value=("ready", evidence)):
        assert (
            bootstrap_cli.main(
                [
                    "--project-root",
                    str(tmp_path),
                    "--profile",
                    "code_app",
                    "--purpose",
                    "Build a portable application harness.",
                    "--stack",
                    "python",
                    "--json",
                ]
            )
            == 0
        )
    capsys.readouterr()
    prior_receipt = (tmp_path / ".mir/bootstrap-receipt.json").read_bytes()
    _write_architecture_evidence(tmp_path, "a" * 40)
    slim_report = {
        "status": "applied",
        "transaction_id": "1" * 32,
        "removed": ["src/mir/provider.py"],
        "preserved_modified": [],
    }

    with (
        patch.object(bootstrap_cli, "_finalize_capabilities", return_value=("ready", evidence)),
        patch.object(bootstrap_cli, "apply_adopter_slim", return_value=slim_report),
        patch.object(bootstrap_cli, "rollback_adopter_slim") as rollback,
        patch.object(bootstrap_cli, "commit_adopter_slim") as commit,
        patch.object(
            bootstrap_cli,
            "_atomic_write_json",
            side_effect=OSError("simulated receipt failure"),
        ),
    ):
        assert (
            bootstrap_cli.main(
                [
                    "--project-root",
                    str(tmp_path),
                    "--profile",
                    "code_app",
                    "--finalize",
                    "--architecture-initialized",
                    "--json",
                ]
            )
            == 1
        )

    failed = json.loads(capsys.readouterr().out)
    assert failed["status"] == "incomplete"
    assert "bootstrap receipt publish failed" in failed["errors"][-1]
    assert (tmp_path / ".mir/bootstrap-receipt.json").read_bytes() == prior_receipt
    rollback.assert_called_once_with(tmp_path, slim_report)
    commit.assert_not_called()


def test_content_workspace_completes_phase2_after_restart(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    _write(
        tmp_path / "career-records" / "timeline.md",
        "# Career timeline\n\nPortableCareerEvidence for prior roles and outcomes.\n",
    )
    capability = {
        "source_commit": "b" * 40,
        "selected_plugins": ["mir-core", "mir-content"],
    }
    phase1 = [
        "--project-root",
        str(tmp_path),
        "--slug",
        "career-harness",
        "--profile",
        "content_workspace",
        "--purpose",
        "Organize career transitions and application evidence.",
        "--stack",
        "markdown,sqlite",
        "--archive",
        "career-history=career-records",
        "--json",
    ]
    with patch.object(bootstrap_cli, "_activate_capabilities", return_value=("ready", capability)):
        assert bootstrap_cli.main(phase1) == 0
    phase1_receipt = json.loads(capsys.readouterr().out)
    assert phase1_receipt["status"] == "restart_required"

    _write_architecture_evidence(tmp_path, "b" * 40)
    with (
        patch.object(
            bootstrap_cli, "_finalize_capabilities", return_value=("ready", capability)
        ),
        patch.object(
            bootstrap_cli,
            "apply_adopter_slim",
            return_value={"status": "already_slim", "removed": [], "preserved_modified": []},
        ),
    ):
        assert (
            bootstrap_cli.main(
                [
                    "--project-root",
                    str(tmp_path),
                    "--slug",
                    "career-harness",
                    "--profile",
                    "content_workspace",
                    "--finalize",
                    "--architecture-initialized",
                    "--json",
                ]
            )
            == 0
        )
    final_receipt = json.loads(capsys.readouterr().out)
    assert final_receipt["status"] == "ready"
    assert final_receipt["content_onboarding"]["status"] == "pass"
    assert final_receipt["architecture_initialization"]["evidence"]["open_gaps"] == 0
    assert all(
        status == "pass"
        for status in final_receipt["architecture_initialization"]["evidence"][
            "full_review"
        ].values()
    )


def test_finalize_refuses_boolean_attestation_without_architecture_outputs(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    with patch.object(
        bootstrap_cli,
        "_activate_capabilities",
        return_value=("ready", {"source_commit": "a" * 40}),
    ):
        assert (
            bootstrap_cli.main(
                [
                    "--project-root",
                    str(tmp_path),
                    "--profile",
                    "code_app",
                    "--purpose",
                    "Build a portable application harness.",
                    "--stack",
                    "python",
                    "--json",
                ]
            )
            == 0
        )
    capsys.readouterr()

    with patch.object(bootstrap_cli, "_finalize_capabilities") as finalize:
        assert (
            bootstrap_cli.main(
                [
                    "--project-root",
                    str(tmp_path),
                    "--profile",
                    "code_app",
                    "--finalize",
                    "--architecture-initialized",
                    "--json",
                ]
            )
            == 1
        )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "incomplete"
    assert report["architecture_initialization"]["attested"] is False
    assert "architecture evidence is missing" in report["capabilities"]["reason"]
    finalize.assert_not_called()


def test_phase2_rejects_incomplete_spec_coverage_and_open_gaps(tmp_path):
    _write_architecture_evidence(tmp_path, "a" * 40)
    evidence_path = tmp_path / "spec" / "bootstrap-evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["coverage"]["l4"] = {
        "total": 10,
        "filled": 9,
        "derived": 0,
        "na": 0,
        "tbd": 1,
    }
    evidence["open_gaps"] = 1
    evidence_path.write_text(json.dumps(evidence) + "\n", encoding="utf-8")
    _write(
        tmp_path / "spec" / "gaps.yaml",
        "gaps:\n  - id: GAP-001\n    status: open\n",
    )

    errors, report = bootstrap_cli._validate_architecture_evidence(tmp_path)

    assert any("l4 still contains TBD" in error for error in errors)
    assert any("contains 1 open gap" in error for error in errors)
    assert report["open_gaps"] == 1


def test_failed_rerun_preserves_existing_db_and_projection(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    assert _bootstrap(tmp_path) == 0
    capsys.readouterr()
    db_path = tmp_path / ".mir" / "memory.db"
    projection_path = tmp_path / "docs" / "memory-map.md"
    db_hash = sha256(db_path.read_bytes()).hexdigest()
    projection = projection_path.read_text(encoding="utf-8")

    (tmp_path / ".claude" / "settings.json").write_text("not json", encoding="utf-8")
    assert _bootstrap(tmp_path) == 1
    capsys.readouterr()

    assert sha256(db_path.read_bytes()).hexdigest() == db_hash
    assert projection_path.read_text(encoding="utf-8") == projection


def test_sync_failure_after_preflight_preserves_live_db(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    assert _bootstrap(tmp_path) == 0
    capsys.readouterr()
    db_path = tmp_path / ".mir" / "memory.db"
    projection_path = tmp_path / "docs" / "memory-map.md"
    db_hash = sha256(db_path.read_bytes()).hexdigest()
    projection = projection_path.read_text(encoding="utf-8")

    with patch.object(bootstrap_cli.context_cli, "main", return_value=1):
        assert _bootstrap(tmp_path) == 1
    capsys.readouterr()

    assert sha256(db_path.read_bytes()).hexdigest() == db_hash
    assert projection_path.read_text(encoding="utf-8") == projection
