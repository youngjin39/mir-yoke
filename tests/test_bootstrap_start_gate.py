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


def _git(project: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _commit(project: Path, message: str = "test") -> str:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Mir Test",
            "GIT_AUTHOR_EMAIL": "mir-test@example.invalid",
            "GIT_COMMITTER_NAME": "Mir Test",
            "GIT_COMMITTER_EMAIL": "mir-test@example.invalid",
        }
    )
    subprocess.run(["git", "add", "."], cwd=project, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", message], cwd=project, check=True, env=env)
    return _git(project, "rev-parse", "HEAD")


def _adoption_manifest(project: Path, source_commit: str) -> None:
    (project / "config").mkdir(parents=True, exist_ok=True)
    (project / "config/bootstrap-adoption.json").write_text(
        json.dumps({"mir_yoke_source_commit": source_commit}) + "\n",
        encoding="utf-8",
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
        '[repo]\nslug = "mir-yoke"\nrepository_type = "public_harness_template"\n',
        encoding="utf-8",
    )
    _git(trusted_yoke, "init", "-q")
    source_commit = _commit(trusted_yoke)
    project = tmp_path / "quoted-project"
    _adoption_manifest(project, source_commit)
    local_adoption = _run_pretool(
        project,
        {
            "tool_name": "Bash",
            "tool_input": {"command": "uv run mir bootstrap-adoption --apply"},
        },
    )
    assert local_adoption.returncode == 0, local_adoption.stderr
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


def test_adoption_recovery_allows_only_pinned_official_detached_worktree(
    tmp_path: Path,
) -> None:
    source = tmp_path / "provider source"
    source.mkdir()
    _git(source, "init", "-q")
    (source / "pyproject.toml").write_text(
        f"[project]\nname = 'mir-yoke-{tmp_path.name}'\n", encoding="utf-8"
    )
    source_commit = _commit(source)
    _git(source, "remote", "add", "origin", "https://github.com/youngjin39/mir-yoke.git")
    (source / "untracked-provider-note.txt").write_text("dirty\n", encoding="utf-8")
    hook_sentinel = tmp_path / "post-checkout-ran"
    post_checkout = source / ".git/hooks/post-checkout"
    post_checkout.write_text(f"#!/bin/sh\ntouch '{hook_sentinel}'\n", encoding="utf-8")
    post_checkout.chmod(0o755)

    project = tmp_path / "adopter"
    _adoption_manifest(project, source_commit)
    (project / ".mir").mkdir()
    (project / ".mir/bootstrap-receipt.json").write_text(
        '{"status":"invalid"}\n', encoding="utf-8"
    )
    temp_root = Path(os.environ.get("TMPDIR", "/tmp")).resolve()
    target = temp_root / f"mir-yoke-bootstrap-{source_commit[:12]}"
    command = (
        "git --no-replace-objects --no-lazy-fetch "
        "-c core.hooksPath=/dev/null -c core.fsmonitor=false "
        f'-c core.attributesFile=/dev/null -C "{source}" '
        f'worktree add --detach "{target}" {source_commit}'
    )

    allowed = _run_pretool(
        project, {"tool_name": "Bash", "tool_input": {"command": command}}
    )
    assert allowed.returncode == 0, allowed.stderr

    _git(
        source,
        "--no-replace-objects",
        "--no-lazy-fetch",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.attributesFile=/dev/null",
        "worktree",
        "add",
        "--detach",
        str(target),
        source_commit,
    )
    assert not hook_sentinel.exists()
    assert not (target / ".mir/repo-profile.toml").exists()

    (target / ".mir").mkdir()
    profile = target / ".mir/repo-profile.toml"
    profile.write_text('[repo]\nslug = "wrong"\n', encoding="utf-8")
    malformed_profile = _run_pretool(
        project,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    f'uv run --project "{target}" '
                    "mir bootstrap-adoption --project-root . --apply --json"
                )
            },
        },
    )
    assert malformed_profile.returncode == 2
    profile.unlink()
    profile.symlink_to(target / "pyproject.toml")
    symlink_profile = _run_pretool(
        project,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    f'uv run --project "{target}" '
                    "mir bootstrap-adoption --project-root . --apply --json"
                )
            },
        },
    )
    assert symlink_profile.returncode == 2
    profile.unlink()

    adoption = _run_pretool(
        project,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    f'uv run --project "{target}" '
                    "mir bootstrap-adoption --project-root . --apply --json"
                )
            },
        },
    )
    assert adoption.returncode == 0, adoption.stderr
    _git(source, "worktree", "remove", "--force", str(target))

    (source / "pyproject.toml").write_text(
        "[project]\nname = 'replacement-commit'\n", encoding="utf-8"
    )
    replacement_commit = _commit(source, "replacement")
    _git(source, "replace", source_commit, replacement_commit)
    replacement_safe = _run_pretool(
        project, {"tool_name": "Bash", "tool_input": {"command": command}}
    )
    assert replacement_safe.returncode == 0, replacement_safe.stderr
    _git(
        source,
        "--no-replace-objects",
        "--no-lazy-fetch",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.attributesFile=/dev/null",
        "worktree",
        "add",
        "--detach",
        str(target),
        source_commit,
    )
    assert "replacement-commit" not in (target / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    _git(source, "worktree", "remove", "--force", str(target))
    _git(source, "replace", "-d", source_commit)

    wrong_target = temp_root / "other-bootstrap-target"
    untrusted = tmp_path / "untrusted"
    subprocess.run(["git", "clone", "-q", str(source), str(untrusted)], check=True)
    _git(untrusted, "remote", "set-url", "origin", "https://example.invalid/mir-yoke.git")

    rejected_commands = (
        command.replace(str(target), str(wrong_target)),
        command.replace(source_commit, "b" * 40),
        command.replace("worktree add --detach", "worktree add --detach --force"),
        command.replace("worktree add --detach", "worktree add --force --detach"),
        command.replace(str(source), str(untrusted)),
        f'git -C "{source}" worktree add --detach "{target}" {source_commit}',
        command.replace(f'"{source}"', str(source)),
        command.replace(f'"{target}"', str(target)),
        (
            f'git -C "{source}; touch {tmp_path / "injected"}" '
            f'worktree add --detach "{target}" {source_commit}'
        ),
        f'git -C "{source}" worktree add --detach "{target}" {source_commit}; touch injected',
    )
    for rejected_command in rejected_commands:
        completed = _run_pretool(
            project,
            {"tool_name": "Bash", "tool_input": {"command": rejected_command}},
        )
        assert completed.returncode == 2, rejected_command

    source_alias = tmp_path / "provider-alias"
    source_alias.symlink_to(source, target_is_directory=True)
    aliased_source = _run_pretool(
        project,
        {
            "tool_name": "Bash",
            "tool_input": {"command": command.replace(str(source), str(source_alias))},
        },
    )
    assert aliased_source.returncode == 2
    source_alias.unlink()

    temp_alias = tmp_path / "temp-alias"
    temp_alias.symlink_to(temp_root, target_is_directory=True)
    aliased_target = _run_pretool(
        project,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": command.replace(
                    str(target), str(temp_alias / target.name)
                )
            },
        },
    )
    assert aliased_target.returncode == 2
    temp_alias.unlink()

    for key, value in (
        ("filter.hostile.smudge", "touch hostile-filter"),
        ("core.fsmonitor", "touch hostile-fsmonitor"),
        ("core.attributesFile", str(tmp_path / "hostile-attributes")),
    ):
        _git(source, "config", key, value)
        unsafe_config = _run_pretool(
            project, {"tool_name": "Bash", "tool_input": {"command": command}}
        )
        assert unsafe_config.returncode == 2, key
        _git(source, "config", "--unset", key)

    info_attributes = source / ".git/info/attributes"
    info_attributes.write_text("* filter=hostile\n", encoding="utf-8")
    unsafe_attributes = _run_pretool(
        project, {"tool_name": "Bash", "tool_input": {"command": command}}
    )
    assert unsafe_attributes.returncode == 2
    info_attributes.unlink()

    target.mkdir()
    existing = _run_pretool(
        project, {"tool_name": "Bash", "tool_input": {"command": command}}
    )
    assert existing.returncode == 2
    target.rmdir()

    target.symlink_to(tmp_path, target_is_directory=True)
    symlink = _run_pretool(
        project, {"tool_name": "Bash", "tool_input": {"command": command}}
    )
    assert symlink.returncode == 2
    target.unlink()

    _git(source, "config", "remote.origin.promisor", "true")
    _git(source, "config", "remote.origin.partialclonefilter", "blob:none")
    object_relative = _git(
        source,
        "rev-parse",
        "--git-path",
        f"objects/{source_commit[:2]}/{source_commit[2:]}",
    )
    object_path = Path(object_relative)
    if not object_path.is_absolute():
        object_path = source / object_path
    object_path.unlink()
    missing_promisor_object = _run_pretool(
        project, {"tool_name": "Bash", "tool_input": {"command": command}}
    )
    assert missing_promisor_object.returncode == 2

    status_source = tmp_path / "status-failure-source"
    status_source.mkdir()
    _git(status_source, "init", "-q")
    (status_source / "pyproject.toml").write_text(
        "[project]\nname = 'status-failure'\n", encoding="utf-8"
    )
    status_commit = _commit(status_source)
    _git(
        status_source,
        "remote",
        "add",
        "origin",
        "https://github.com/youngjin39/mir-yoke.git",
    )
    _adoption_manifest(project, status_commit)
    (status_source / ".git/index").write_bytes(b"corrupt-index")
    failed_status = _run_pretool(
        project,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    f'uv run --project "{status_source}" '
                    "mir bootstrap-adoption --project-root . --apply --json"
                )
            },
        },
    )
    assert failed_status.returncode == 2


def test_bootstrap_commands_are_mode_aware(tmp_path: Path) -> None:
    no_manifest = _run_pretool(
        tmp_path / "greenfield",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "uv run mir bootstrap-adoption --apply"},
        },
    )
    assert no_manifest.returncode == 2

    adopted = tmp_path / "adopted"
    (adopted / "config").mkdir(parents=True)
    (adopted / "config/bootstrap-adoption.json").write_text("{}\n", encoding="utf-8")
    for command in (
        "./setup.sh --profile code_app --purpose app --stack python",
        "uv run mir bootstrap --profile code_app --purpose app --stack python",
    ):
        completed = _run_pretool(
            adopted,
            {"tool_name": "Bash", "tool_input": {"command": command}},
        )
        assert completed.returncode == 2, command


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


def test_missing_receipt_allows_only_single_declared_evidence_git_add(
    tmp_path: Path,
) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "bootstrap-adoption.json").write_text(
        json.dumps(
            {
                "surfaces": {
                    "phase2_spec": {
                        "evidence_paths": [
                            "docs/native-spec.md",
                            "docs/native spec.md",
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec/bootstrap-adoption-review.yaml").write_text(
        "review: ready\n", encoding="utf-8"
    )
    (tmp_path / 'spec/"bootstrap-adoption-review.yaml"').write_text(
        "decoy: true\n", encoding="utf-8"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/native-spec.md").write_text("ready\n", encoding="utf-8")
    (tmp_path / "docs/native spec.md").write_text("ready\n", encoding="utf-8")
    for command in (
        "git add -- config/bootstrap-adoption.json",
        "git add -- spec/bootstrap-adoption-review.yaml",
        "git add -- docs/native-spec.md",
        "git add -- 'docs/native spec.md'",
    ):
        completed = _run_pretool(
            tmp_path,
            {"tool_name": "Bash", "tool_input": {"command": command}},
        )
        assert completed.returncode == 0, command

    for command in (
        "git add -- src/application.py",
        "git add -A",
        "git add -- spec/a.yaml spec/b.yaml",
        "git add -- ':(glob)spec/**'",
        "git add -- spec/{a,b}.yaml",
        "git add -- 'spec/$FILES.yaml'",
        'git add -- spec/"bootstrap-adoption-review.yaml"',
        "git add -- spec/evidence-dir",
        "git add -- ../other/spec/evidence.yaml",
    ):
        if command.endswith("spec/evidence-dir"):
            (tmp_path / "spec/evidence-dir").mkdir()
            (tmp_path / "spec/evidence-dir/nested.yaml").write_text(
                "ready: false\n", encoding="utf-8"
            )
        completed = _run_pretool(
            tmp_path,
            {"tool_name": "Bash", "tool_input": {"command": command}},
        )
        assert completed.returncode == 2, command

    (tmp_path / "config/bootstrap-adoption.json").unlink()
    deleted_manifest = _run_pretool(
        tmp_path,
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git add -- config/bootstrap-adoption.json"},
        },
    )
    assert deleted_manifest.returncode == 2


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

    deleted_manifest = _run_pretool(
        tmp_path,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "\n".join(
                    (
                        "apply_patch <<'PATCH'",
                        "*** Begin Patch",
                        "*** Delete File: config/bootstrap-adoption.json",
                        "*** End Patch",
                        "PATCH",
                    )
                )
            },
        },
    )
    assert deleted_manifest.returncode == 2


def test_forged_template_profile_does_not_bypass_bootstrap(tmp_path: Path) -> None:
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir/repo-profile.toml").write_text(
        '[repo]\nslug = "mir-yoke"\nrepository_type = "public_harness_template"\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    completed = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "src/application.py"}},
    )

    assert completed.returncode == 2


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
        "uv run ruff check .",
        "uv run ruff check --output-file src/unauthorized.py .",
        "uv run ruff check -o src/unauthorized.py .",
        "uv run ruff check --cache-dir src/cache .",
        "uv run pytest spec/evil.py",
        "uv run pytest --rootdir /tmp/other /tmp/other/test_evil.py",
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
    runtime_root = tmp_path.parent / f"{tmp_path.name}-runtime"
    external_cli = runtime_root / "bin/mir"
    dependency = runtime_root / "tools/dependency.py"
    external_cli.parent.mkdir(parents=True)
    dependency.parent.mkdir(parents=True)
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    external_cli.write_text(
        "#!/bin/sh\n"
        'if [ "$1 $2" = "runtime-manifest verify" ]; then '
        f"grep -q 'VALUE = 1' '{dependency}'; exit $?; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    external_cli.chmod(0o755)
    runtime_manifest = runtime_root / "runtime-manifest.json"
    runtime_manifest.write_text('{"schema_version":1}\n', encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config/adopter-boundary.json").write_text(
        json.dumps(
            {
                "provider_markers": ["src/mir"],
                "provider_text_markers": [
                    {"path": "CLAUDE.md", "contains": "provider contract"}
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text("# Product contract\n", encoding="utf-8")
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir/bootstrap-receipt.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "cli": {
                    "externalized": True,
                    "executable": str(external_cli),
                    "sha256": hashlib.sha256(external_cli.read_bytes()).hexdigest(),
                    "runtime_manifest": str(runtime_manifest),
                    "runtime_manifest_sha256": hashlib.sha256(
                        runtime_manifest.read_bytes()
                    ).hexdigest(),
                    "source_url": "https://github.com/example/mir-yoke.git",
                    "source_commit": "a" * 40,
                    "constraints_sha256": "b" * 64,
                },
                "slim": {"status": "applied", "transaction_id": "a" * 32},
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

    dependency.write_text("VALUE = 2\n", encoding="utf-8")
    changed_dependency = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "notes.txt"}},
    )
    assert changed_dependency.returncode == 2
    dependency.write_text("VALUE = 1\n", encoding="utf-8")

    external_cli.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    changed_cli = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "notes.txt"}},
    )
    assert changed_cli.returncode == 2


def test_restart_required_receipt_blocks_phase2_when_runtime_closure_drifts(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path.parent / f"{tmp_path.name}-restart-runtime"
    cli = runtime_root / "bin/mir"
    dependency = runtime_root / "tools/dependency.py"
    cli.parent.mkdir(parents=True)
    dependency.parent.mkdir(parents=True)
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    cli.write_text(
        "#!/bin/sh\n"
        'if [ "$1 $2" = "runtime-manifest verify" ]; then '
        f"grep -q 'VALUE = 1' '{dependency}'; exit $?; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    manifest = runtime_root / "runtime-manifest.json"
    manifest.write_text('{"schema_version":1}\n', encoding="utf-8")
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir/bootstrap-receipt.json").write_text(
        json.dumps(
            {
                "status": "restart_required",
                "cli": {
                    "externalized": True,
                    "executable": str(cli),
                    "sha256": hashlib.sha256(cli.read_bytes()).hexdigest(),
                    "runtime_manifest": str(manifest),
                    "runtime_manifest_sha256": hashlib.sha256(
                        manifest.read_bytes()
                    ).hexdigest(),
                    "source_url": "https://github.com/example/mir-yoke.git",
                    "source_commit": "a" * 40,
                    "constraints_sha256": "b" * 64,
                },
            }
        ),
        encoding="utf-8",
    )

    allowed = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "spec/STATE.md"}},
    )
    assert allowed.returncode == 0, allowed.stderr

    dependency.write_text("VALUE = 2\n", encoding="utf-8")
    blocked = _run_pretool(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "spec/STATE.md"}},
    )
    assert blocked.returncode == 2
    assert "bootstrap is invalid" in blocked.stderr


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
    assert "run setup.sh with --profile" in completed.stdout
    assert "inside WSL on Windows hosts" in completed.stdout
    assert "setup.sh/setup.ps1" not in completed.stdout


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
    assert "scripts/mir.sh bootstrap-adoption --apply" in completed.stdout
    assert "run setup.sh/setup.ps1" not in completed.stdout


def test_hooks_use_only_the_managed_python_launcher() -> None:
    launcher = HOOKS / "_lib" / "run-python.sh"
    assert launcher.is_file()
    assert os.access(launcher, os.X_OK)
    assert ".venv/bin/python" in launcher.read_text(encoding="utf-8")
    assert "bootstrap-receipt.json" in launcher.read_text(encoding="utf-8")
    assert "run-python" in launcher.read_text(encoding="utf-8")
    for hook in HOOKS.rglob("*.sh"):
        if hook == launcher:
            continue
        assert "python3" not in hook.read_text(encoding="utf-8"), hook
