"""Test that every shipped .ai-harness/deny-list.yaml rule actually enforces.

ADR-87. These tests exist because the deny-list was inert for its whole life and
nothing noticed: the awk field reader stripped only double quotes while every
shipped pattern is single-quoted, so each regex reached `grep -E` with a literal
leading apostrophe.

Two design rules keep this test honest:

1. Assert on the reason emitted to stderr, never on the exit code alone. The hook
   exits 2 for many unrelated reasons -- BootstrapGate, a malformed payload, a
   hardcoded guard -- so `returncode == 2` cannot show that a deny-list rule was
   the thing that fired. Asserting `deny-list[<id>]` can.
2. Run against a project fixture that reaches `template_maintainer` gate state.
   A bare tmp_path is blocked by BootstrapGate before the deny-list is consulted,
   which would make every assertion pass for the wrong reason.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DENY_LIST = ROOT / ".ai-harness" / "deny-list.yaml"
HOOK = ROOT / ".claude" / "hooks" / "pre-tool-use.sh"

# Rules with no hardcoded-guard equivalent. These are the shapes that were
# genuinely unprotected while the deny-list was inert, so they are the
# regression anchors that matter most.
DENY_LIST_ONLY = ("dd-of-device", "protected-secrets-dir", "chmod-777-recursive")


def _parse_rules() -> list[dict[str, str]]:
    """Read id/pattern/severity straight from the shipped YAML.

    Deliberately not a YAML library call: the hook parses this file with awk, and
    this test must fail if the file grows a shape the hook cannot read.
    """
    rules: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw in DENY_LIST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("- id:"):
            if current:
                rules.append(current)
            current = {"id": line.split(":", 1)[1].strip().strip("\"'")}
        elif current and line.startswith(("pattern:", "severity:", "reason:")):
            key, value = line.split(":", 1)
            current[key.strip()] = value.strip().strip("\"'")
    if current:
        rules.append(current)
    return rules


def _make_project(tmp_path: Path) -> Path:
    """Build a checkout the bootstrap gate accepts as the Yoke maintainer.

    mir_bootstrap_gate_state() returns `template_maintainer` for a profile
    declaring the mir-yoke slug and public_harness_template type whose origin is
    an official Mir Yoke URL. Without this the gate short-circuits every call.
    """
    project = tmp_path / "yoke"
    (project / ".mir").mkdir(parents=True)
    (project / ".ai-harness").mkdir()
    (project / ".claude" / "hooks" / "_lib").mkdir(parents=True)
    (project / ".mir" / "repo-profile.toml").write_text(
        '[repo]\nslug = "mir-yoke"\nrepository_type = "public_harness_template"\n',
        encoding="utf-8",
    )
    shutil.copy(DENY_LIST, project / ".ai-harness" / "deny-list.yaml")
    shutil.copy(HOOK, project / ".claude" / "hooks" / "pre-tool-use.sh")
    for helper in (ROOT / ".claude" / "hooks" / "_lib").glob("*.sh"):
        shutil.copy(helper, project / ".claude" / "hooks" / "_lib" / helper.name)
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/youngjin39/mir-yoke.git"],
        cwd=project,
        check=True,
    )
    gate = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{project}/.claude/hooks/_lib/bootstrap-gate.sh"; '
            f'mir_bootstrap_gate_state "{project}"',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert gate.stdout.strip() == "template_maintainer", (
        "fixture must reach template_maintainer or the deny-list is never "
        f"consulted; got {gate.stdout.strip()!r}"
    )
    return project


def _run(project: Path, payload: dict) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(project)
    return subprocess.run(
        ["/bin/bash", str(project / ".claude" / "hooks" / "pre-tool-use.sh")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=project,
        env=env,
    )


def _install_deny_list(project: Path, body: str) -> None:
    """Replace the project's deny-list with a probe rule set."""
    (project / ".ai-harness" / "deny-list.yaml").write_text(body, encoding="utf-8")


def _bash(project: Path, command: str) -> subprocess.CompletedProcess:
    return _run(
        project,
        {"tool_name": "Bash", "cwd": str(project), "tool_input": {"command": command}},
    )


def _write(project: Path, file_path: str) -> subprocess.CompletedProcess:
    return _run(
        project,
        {
            "tool_name": "Write",
            "cwd": str(project),
            "tool_input": {"file_path": file_path, "content": "x"},
        },
    )


def test_every_pattern_is_a_usable_posix_regex(tmp_path: Path) -> None:
    """A pattern grep cannot compile is a silent hole, and \\s/\\b are not POSIX.

    The hook matches with `grep -E`. GNU grep accepts \\s and \\b as extensions;
    BSD grep on the macOS CI runner is not guaranteed to. Because the patterns
    never matched anywhere until ADR-87, no evidence exists that they behave the
    same on both runners, so POSIX classes are required.
    """
    rules = _parse_rules()
    assert rules, "deny-list.yaml parsed to zero rules"
    for rule in rules:
        pattern = rule.get("pattern", "")
        assert pattern, f"{rule['id']} has no pattern"
        assert not pattern.startswith(("'", '"')), (
            f"{rule['id']} pattern keeps its YAML quote: {pattern!r} -- the hook "
            "would match a literal quote character"
        )
        assert "\\s" not in pattern and "\\b" not in pattern, (
            f"{rule['id']} uses the non-POSIX escape \\s or \\b: {pattern!r}; "
            "use [[:space:]] and an explicit boundary instead"
        )
        probe = subprocess.run(
            ["grep", "-qE", pattern],
            input="deny-list regex compile probe\n",
            text=True,
            capture_output=True,
            check=False,
        )
        assert probe.returncode in (0, 1), (
            f"{rule['id']} pattern does not compile under grep -E: "
            f"{probe.stderr.strip()}"
        )


def test_declared_severities_are_known(tmp_path: Path) -> None:
    for rule in _parse_rules():
        assert rule.get("severity") in {"block", "warn", "suggest"}, (
            f"{rule['id']} declares an unknown severity {rule.get('severity')!r}"
        )


def test_deny_list_only_rules_still_ship() -> None:
    """These three shapes have no hardcoded-guard fallback.

    If one is renamed or dropped, the protection disappears with it and no other
    test would notice, which is exactly how the original regression survived.
    """
    shipped = {rule["id"] for rule in _parse_rules()}
    missing = [rule_id for rule_id in DENY_LIST_ONLY if rule_id not in shipped]
    assert not missing, (
        f"deny-list-only rules disappeared: {missing}. These have no hardcoded "
        "guard, so removing them removes the protection entirely."
    )


@pytest.mark.parametrize(
    ("rule_id", "command"),
    [
        ("rm-rf-root", "rm -rf /"),
        ("rm-rf-home", "rm -rf $HOME"),
        ("dd-of-device", "dd if=/dev/zero of=/dev/nvme0n1"),
        ("skip-pre-commit-hooks", "git commit -m x --no-verify"),
        # Blocked by hook guard 2, which ANDs "force flag" with "protected
        # branch". The flag-after-refspec spellings are the reason ADR-87 rewrites
        # it: they were allowed while the canonical spelling was blocked.
        ("guard-force-push-protected", "git push --force origin main"),
        ("guard-force-push-protected", "git push origin main --force"),
        ("guard-force-push-protected", "git push origin main -f"),
    ],
)
def test_block_severity_commands_are_blocked(
    tmp_path: Path, rule_id: str, command: str
) -> None:
    project = _make_project(tmp_path)
    result = _bash(project, command)
    assert result.returncode == 2, (
        f"{command!r} must be blocked; got rc={result.returncode} "
        f"stderr={result.stderr.strip()!r}"
    )
    assert "grep:" not in result.stderr, (
        f"a guard regex failed to compile while screening {command!r}: "
        f"{result.stderr.strip()!r}"
    )


@pytest.mark.parametrize(
    "file_path",
    ["secrets/prod.yaml", "config/secrets/tokens.json"],
)
def test_secrets_directory_writes_are_blocked(tmp_path: Path, file_path: str) -> None:
    """The hardcoded secret guard tests a basename, so it cannot cover a directory."""
    project = _make_project(tmp_path)
    result = _write(project, str(project / file_path))
    assert result.returncode == 2, (
        f"write to {file_path} must be blocked; got rc={result.returncode} "
        f"stderr={result.stderr.strip()!r}"
    )
    assert "deny-list[protected-secrets-dir]" in result.stderr, (
        "the deny-list rule must be the thing that reports it -- rc=2 alone can "
        f"come from any other guard; stderr={result.stderr.strip()!r}"
    )


@pytest.mark.parametrize(
    "file_path",
    ["secrets/prod.yaml", "./secrets/prod.yaml", "config/secrets/tokens.json"],
)
def test_secrets_directory_writes_are_blocked_for_relative_paths(
    tmp_path: Path, file_path: str
) -> None:
    """A repo-relative path is the spelling an agent writes most often.

    The absolute-path cases above passed while `secrets/prod.yaml` was allowed,
    because the subject handed to the path rules carried a `$TOOL_NAME ` prefix
    and `(^|/)secrets/` could only match on the `/`.
    """
    project = _make_project(tmp_path)
    result = _write(project, file_path)
    assert result.returncode == 2, (
        f"write to {file_path} must be blocked; got rc={result.returncode} "
        f"stderr={result.stderr.strip()!r}"
    )
    assert "deny-list[protected-secrets-dir]" in result.stderr, (
        f"stderr={result.stderr.strip()!r}"
    )


def test_path_deny_list_anchors_at_the_path(tmp_path: Path) -> None:
    """`^` in a path pattern must anchor at the path itself.

    Uses a probe rule rather than a shipped one so this fails for exactly one
    reason: the subject passed to the path rules is not the bare path.
    """
    project = _make_project(tmp_path)
    _install_deny_list(
        project,
        "- id: probe-anchor\n"
        "  pattern: '^probe/'\n"
        "  severity: block\n"
        '  reason: "probe rule"\n',
    )
    result = _write(project, "probe/file.txt")
    assert "deny-list[probe-anchor]" in result.stderr, (
        "an anchored path pattern never matched, so the subject is not the bare "
        f"path; rc={result.returncode} stderr={result.stderr.strip()!r}"
    )


def test_apply_patch_target_paths_are_screened(tmp_path: Path) -> None:
    """apply_patch had a path screen, but it never consulted the deny-list.

    `_mir_patch_path_safety_reason` already covered outside-root, `.git`
    internals and secret basenames -- which is why the `.env` case below passed
    before this change -- but a patch adding `secrets/prod.yaml` was allowed,
    because `protected-secrets-dir` lives only in the deny-list.
    """
    project = _make_project(tmp_path)
    patch = (
        "*** Begin Patch\n"
        "*** Add File: secrets/prod.yaml\n"
        "+token: x\n"
        "*** End Patch\n"
    )
    result = _run(
        project,
        {"tool_name": "apply_patch", "cwd": str(project), "tool_input": {"command": patch}},
    )
    assert "deny-list[protected-secrets-dir]" in result.stderr, (
        f"rc={result.returncode} stderr={result.stderr.strip()!r}"
    )

    env_patch = (
        "*** Begin Patch\n*** Add File: .env\n+TOKEN=x\n*** End Patch\n"
    )
    env_result = _run(
        project,
        {
            "tool_name": "apply_patch",
            "cwd": str(project),
            "tool_input": {"command": env_patch},
        },
    )
    assert env_result.returncode == 2, (
        f"a patch that adds .env must be blocked; stderr={env_result.stderr.strip()!r}"
    )


def test_notebook_edit_path_is_screened(tmp_path: Path) -> None:
    """NotebookEdit carries its target in `notebook_path` and reached no guard."""
    project = _make_project(tmp_path)
    result = _run(
        project,
        {
            "tool_name": "NotebookEdit",
            "cwd": str(project),
            "tool_input": {"notebook_path": "secrets/analysis.ipynb"},
        },
    )
    assert "deny-list[protected-secrets-dir]" in result.stderr, (
        f"rc={result.returncode} stderr={result.stderr.strip()!r}"
    )


def test_deny_list_only_rules_report_their_own_id(tmp_path: Path) -> None:
    """Exit code 2 alone cannot prove the deny-list fired -- the reason can.

    These three shapes have no hardcoded-guard equivalent, so the deny-list is
    the only thing that can report them.
    """
    project = _make_project(tmp_path)
    cases = {
        "dd-of-device": "dd if=/dev/zero of=/dev/nvme0n1",
        "chmod-777-recursive": "chmod -R 777 /srv",
    }
    for rule_id, command in cases.items():
        result = _bash(project, command)
        assert f"deny-list[{rule_id}]" in result.stderr, (
            f"{command!r} must be reported by deny-list[{rule_id}]; "
            f"stderr={result.stderr.strip()!r}"
        )


def test_plus_refspec_force_push_to_protected_branch_is_blocked(tmp_path: Path) -> None:
    """A leading `+` on the refspec forces the update with no flag at all.

    `git push origin +main` rewrites remote history exactly as
    `git push --force origin main` does, but guard 2 tested only for
    `-f`/`--force*` and so allowed it.
    """
    project = _make_project(tmp_path)
    for command in (
        "git push origin +main",
        "git push origin +master",
        "git push origin +refs/heads/main",
    ):
        result = _bash(project, command)
        assert result.returncode == 2, (
            f"{command!r} must be blocked; got rc={result.returncode} "
            f"stderr={result.stderr.strip()!r}"
        )
        assert "grep:" not in result.stderr, result.stderr


def test_plus_refspec_on_an_unprotected_branch_is_allowed(tmp_path: Path) -> None:
    """Force-pushing your own topic branch stays ordinary work.

    Guards the `+` clause against becoming a blanket ban on the `+` syntax.
    """
    project = _make_project(tmp_path)
    for command in (
        "git push origin +feature/login",
        "git push origin +refs/heads/feature/login",
    ):
        result = _bash(project, command)
        assert result.returncode == 0, (
            f"{command!r} must be allowed; got rc={result.returncode} "
            f"stderr={result.stderr.strip()!r}"
        )


def test_sudo_is_blocked_regardless_of_position(tmp_path: Path) -> None:
    """`(^| )sudo( |$)` misses a shell separator and an absolute path."""
    project = _make_project(tmp_path)
    for command in (
        "sudo systemctl stop firewalld",
        "echo x;sudo systemctl stop firewalld",
        "echo x && sudo systemctl stop firewalld",
        "/usr/bin/sudo systemctl stop firewalld",
    ):
        result = _bash(project, command)
        assert result.returncode == 2, (
            f"{command!r} must be blocked; got rc={result.returncode} "
            f"stderr={result.stderr.strip()!r}"
        )


def test_ordinary_commands_and_paths_are_allowed(tmp_path: Path) -> None:
    """Guard against over-blocking, including branches that merely contain 'main'.

    The previous unanchored `(main|master|release)` match blocked `maintenance`
    and `my-release-notes` by accident.
    """
    project = _make_project(tmp_path)
    for command in (
        "ls -la",
        "git status --short",
        "git push origin feature/login",
        "git push --force origin maintenance",
        "git push --force origin my-release-notes",
    ):
        result = _bash(project, command)
        assert result.returncode == 0, (
            f"{command!r} must be allowed; got rc={result.returncode} "
            f"stderr={result.stderr.strip()!r}"
        )
    allowed = _write(project, str(project / "docs" / "notes.md"))
    assert allowed.returncode == 0, allowed.stderr


def test_no_unsubstituted_placeholder_in_hooks() -> None:
    """A sanitized placeholder left inside a regex broke F9 and aborted grep."""
    offenders = []
    for hook in sorted((ROOT / ".claude" / "hooks").rglob("*.sh")):
        text = hook.read_text(encoding="utf-8")
        if re.search(r"<your-[a-z-]+>", text):
            offenders.append(str(hook.relative_to(ROOT)))
    assert not offenders, (
        f"hooks still contain an unsubstituted placeholder: {offenders}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
