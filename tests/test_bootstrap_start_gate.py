from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".claude" / "hooks"


def _copy_hooks(project: Path) -> Path:
    target = project / ".claude" / "hooks"
    shutil.copytree(HOOKS, target, dirs_exist_ok=True)
    return target


def _run_pretool(project: Path, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    hooks = _copy_hooks(project)
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(project)
    return subprocess.run(
        ["bash", str(hooks / "pre-tool-use.sh")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_missing_receipt_blocks_normal_mutation(tmp_path: Path) -> None:
    completed = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "src/application.py"}},
    )

    assert completed.returncode == 2
    assert "BootstrapGate BLOCK" in completed.stderr


def test_missing_receipt_allows_phase2_spec_evidence(tmp_path: Path) -> None:
    completed = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "spec/STATE.md"}},
    )
    assert completed.returncode == 0, completed.stderr


def test_missing_receipt_allows_setup_and_bootstrap_commands(tmp_path: Path) -> None:
    for command in (
        './setup.sh --profile content_workspace --purpose "Career records" --stack markdown',
        "uv run mir bootstrap --profile content_workspace --purpose records --stack markdown",
        "uv run mir bootstrap-adoption --apply",
    ):
        project = tmp_path / str(len(command))
        project.mkdir()
        completed = _run_pretool(
            project,
            {"tool_name": "Bash", "tool_input": {"command": command}},
        )
        assert completed.returncode == 0, completed.stderr

    trusted_yoke = tmp_path / "Trusted Yoke"
    (trusted_yoke / ".mir").mkdir(parents=True)
    (trusted_yoke / ".mir/repo-profile.toml").write_text(
        '[repo]\nrepository_type = "public_harness_template"\n', encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=trusted_yoke, check=True)
    subprocess.run(["git", "add", ".mir/repo-profile.toml"], cwd=trusted_yoke, check=True)
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Mir Test",
            "GIT_AUTHOR_EMAIL": "mir-test@example.invalid",
            "GIT_COMMITTER_NAME": "Mir Test",
            "GIT_COMMITTER_EMAIL": "mir-test@example.invalid",
        }
    )
    subprocess.run(["git", "commit", "-qm", "test"], cwd=trusted_yoke, check=True, env=env)
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=trusted_yoke,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    project = tmp_path / "quoted-project"
    (project / "config").mkdir(parents=True)
    (project / "config/bootstrap-adoption.json").write_text(
        json.dumps({"mir_yoke_source_commit": source_commit}) + "\n",
        encoding="utf-8",
    )
    quoted_project = _run_pretool(
        project,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    f'uv run --project "{trusted_yoke}" '
                    "mir bootstrap-adoption --project-root . --apply --json"
                )
            },
        },
    )
    assert quoted_project.returncode == 0, quoted_project.stderr

    (trusted_yoke / "untracked.py").write_text("print('unsafe')\n", encoding="utf-8")
    dirty_source = _run_pretool(
        project,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    f'uv run --project "{trusted_yoke}" '
                    "mir bootstrap-adoption --project-root . --apply --json"
                )
            },
        },
    )
    assert dirty_source.returncode == 2


def test_adoption_manifest_allows_only_declared_evidence_edits(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "bootstrap-adoption.json").write_text(
        json.dumps(
            {
                "surfaces": {
                    "phase2_spec": {"evidence_paths": ["docs/native-spec.md"]}
                }
            }
        ),
        encoding="utf-8",
    )
    for path in (
        "config/bootstrap-adoption.json",
        "config/content-onboarding.json",
        "docs/native-spec.md",
    ):
        completed = _run_pretool(
            tmp_path,
            {"tool_name": "Write", "tool_input": {"file_path": path}},
        )
        assert completed.returncode == 0, completed.stderr

    blocked = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "src/application.py"}},
    )
    assert blocked.returncode == 2


def test_adoption_gate_accepts_codex_shell_wrapped_apply_patch(tmp_path: Path) -> None:
    allowed = _run_pretool(
        tmp_path,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "\n".join(
                    (
                        "apply_patch <<'PATCH'",
                        "*** Begin Patch",
                        "*** Add File: config/bootstrap-adoption.json",
                        "+{}",
                        "*** End Patch",
                        "PATCH",
                    )
                )
            },
        },
    )
    assert allowed.returncode == 0, allowed.stderr

    blocked = _run_pretool(
        tmp_path,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "\n".join(
                    (
                        "apply_patch <<'PATCH'",
                        "*** Begin Patch",
                        "*** Add File: src/application.py",
                        "+jq is not an authorization token",
                        "*** End Patch",
                        "PATCH",
                    )
                )
            },
        },
    )
    assert blocked.returncode == 2

    for escaped_path in (
        "../other/spec/unauthorized.yaml",
        "/tmp/other/spec/unauthorized.yaml",
        r"C:\other\spec\unauthorized.yaml",
    ):
        escaped = _run_pretool(
            tmp_path,
            {
                "tool_name": "Bash",
                "tool_input": {
                    "command": "\n".join(
                        (
                            "apply_patch <<'PATCH'",
                            "*** Begin Patch",
                            f"*** Add File: {escaped_path}",
                            "+unauthorized: true",
                            "*** End Patch",
                            "PATCH",
                        )
                    )
                },
            },
        )
        assert escaped.returncode == 2, escaped_path

    symlinked_spec = tmp_path / "symlinked"
    symlinked_spec.mkdir()
    (tmp_path / "spec").symlink_to(symlinked_spec, target_is_directory=True)
    linked = _run_pretool(
        tmp_path,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "spec/evidence.yaml"},
        },
    )
    assert linked.returncode == 2

    moved = _run_pretool(
        tmp_path,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "\n".join(
                    (
                        "apply_patch <<'PATCH'",
                        "*** Begin Patch",
                        "*** Update File: spec/evidence.yaml",
                        "*** Move to: src/unauthorized.py",
                        "@@",
                        "-old",
                        "+new",
                        "*** End Patch",
                        "PATCH",
                    )
                )
            },
        },
    )
    assert moved.returncode == 2


def test_missing_receipt_rejects_compound_safe_command_and_patch_suffix(
    tmp_path: Path,
) -> None:
    for command in (
        "touch src/unauthorized.py; git status",
        "git status; touch src/unauthorized.py",
        "\n".join(
            (
                "apply_patch <<'PATCH'",
                "*** Begin Patch",
                "*** Add File: config/bootstrap-adoption.json",
                "+{}",
                "*** End Patch",
                "PATCH",
                "touch src/unauthorized.py",
            )
        ),
    ):
        completed = _run_pretool(
            tmp_path,
            {"tool_name": "Bash", "tool_input": {"command": command}},
        )
        assert completed.returncode == 2


def test_missing_receipt_rejects_mutating_or_wrapped_shell_commands(tmp_path: Path) -> None:
    for command in (
        "sed -i.bak 's/a/b/' config/bootstrap-adoption.json",
        "find spec -type f -delete",
        "jq . config/bootstrap-adoption.json > spec/copied.json",
        "git diff --output=spec/diff.txt",
        "uv run ruff format spec",
        "uv run python -c 'print(1)' mir bootstrap",
        "ls $(touch spec/unauthorized.yaml)",
    ):
        completed = _run_pretool(
            tmp_path,
            {"tool_name": "Bash", "tool_input": {"command": command}},
        )
        assert completed.returncode == 2, command

    for command in (
        "uv run mir bootstrap-adoption --project-root /tmp/other --apply",
        "uv run mir bootstrap-adoption --project-r /tmp/other --apply",
    ):
        completed = _run_pretool(
            tmp_path,
            {"tool_name": "Bash", "tool_input": {"command": command}},
        )
        assert completed.returncode == 2, command

    external_workdir = tmp_path / "other"
    external_workdir.mkdir()
    completed = _run_pretool(
        tmp_path,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "uv run mir bootstrap-adoption --apply",
                "workdir": str(external_workdir),
            },
        },
    )
    assert completed.returncode == 2


def test_adoption_ready_receipt_binds_manifest_source_and_evidence(tmp_path: Path) -> None:
    manifest = tmp_path / "config" / "bootstrap-adoption.json"
    evidence = tmp_path / "spec" / "evidence.yaml"
    manifest.parent.mkdir()
    evidence.parent.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "mir_yoke_source_commit": "a" * 40,
                "surfaces": {
                    "phase2_spec": {"evidence_paths": ["spec/evidence.yaml"]}
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    evidence.write_text("verified: true\n", encoding="utf-8")
    receipt = {
        "status": "ready",
        "source": {"mir_yoke_commit": "a" * 40},
        "manifest": {"sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()},
        "evidence": [
            {
                "path": "spec/evidence.yaml",
                "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            }
        ],
    }
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir" / "bootstrap-receipt.json").write_text(
        json.dumps(receipt) + "\n", encoding="utf-8"
    )

    ready = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "notes.txt"}},
    )
    assert ready.returncode == 0

    evidence.write_text("verified: false\n", encoding="utf-8")
    stale = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "notes.txt"}},
    )
    assert stale.returncode == 2
    assert "bootstrap is invalid" in stale.stderr

    evidence.write_text("verified: true\n", encoding="utf-8")
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    stale_manifest = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "notes.txt"}},
    )
    assert stale_manifest.returncode == 2


def test_ready_receipt_requires_the_complete_declared_evidence_set(tmp_path: Path) -> None:
    manifest = tmp_path / "config/bootstrap-adoption.json"
    evidence = tmp_path / "spec/evidence.yaml"
    manifest.parent.mkdir()
    evidence.parent.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "mir_yoke_source_commit": "a" * 40,
                "surfaces": {
                    "phase2_spec": {
                        "evidence_paths": ["spec/evidence.yaml", "spec/omitted.yaml"]
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    evidence.write_text("verified: true\n", encoding="utf-8")
    (tmp_path / "spec/omitted.yaml").write_text("verified: true\n", encoding="utf-8")
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir/bootstrap-receipt.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "source": {"mir_yoke_commit": "a" * 40},
                "manifest": {"sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()},
                "evidence": [
                    {
                        "path": "spec/evidence.yaml",
                        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    completed = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "notes.txt"}},
    )
    assert completed.returncode == 2


def test_unbound_ready_receipt_does_not_release_normal_mutation(tmp_path: Path) -> None:
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir" / "bootstrap-receipt.json").write_text(
        '{"status":"ready"}\n', encoding="utf-8"
    )

    completed = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "notes.txt"}},
    )

    assert completed.returncode == 2


def test_hash_bound_greenfield_ready_receipt_releases_normal_mutation(
    tmp_path: Path,
) -> None:
    output_hashes: dict[str, str] = {}
    for relative in (
        "spec/STATE.md",
        "spec/index.yaml",
        "spec/graph.yaml",
        "spec/gaps.yaml",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"verified: {relative}\n", encoding="utf-8")
        output_hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir/bootstrap-receipt.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "capabilities": {"status": "ready"},
                "architecture_initialization": {
                    "attested": True,
                    "evidence": {"output_hashes": output_hashes},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    completed = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "notes.txt"}},
    )
    assert completed.returncode == 0, completed.stderr


def test_session_start_requires_bootstrap_without_running_python(tmp_path: Path) -> None:
    hooks = _copy_hooks(tmp_path)
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["PATH"] = "/usr/bin:/bin"

    completed = subprocess.run(
        ["bash", str(hooks / "session-start.sh")],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert "bootstrap_gate: required (state=missing)" in completed.stdout
    assert "normal_mutation: blocked" in completed.stdout


def test_session_start_routes_existing_repository_to_adoption(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "bootstrap-adoption.json").write_text("{}\n", encoding="utf-8")
    hooks = _copy_hooks(tmp_path)
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["PATH"] = "/usr/bin:/bin"

    completed = subprocess.run(
        ["bash", str(hooks / "session-start.sh")],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert "uv run mir bootstrap-adoption --apply" in completed.stdout
    assert "run setup.sh/setup.ps1" not in completed.stdout


def test_hooks_use_only_the_managed_python_launcher() -> None:
    launcher = HOOKS / "_lib" / "run-python.sh"
    assert launcher.is_file()
    assert os.access(launcher, os.X_OK)
    assert ".venv/bin/python" in launcher.read_text(encoding="utf-8")
    assert "uv run --project" in launcher.read_text(encoding="utf-8")
    for hook in HOOKS.rglob("*.sh"):
        if hook == launcher:
            continue
        assert "python3" not in hook.read_text(encoding="utf-8"), hook
