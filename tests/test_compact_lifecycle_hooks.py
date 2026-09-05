"""Regression tests for the repository-owned compact lifecycle."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".claude" / "hooks"
EVIDENCE = Path(".mir/runtime/hook-invocations.jsonl")


def _run_hook(
    name: str,
    project_dir: Path,
    payload: dict[str, object],
    *,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env["MIR_COMPACT_PYTHON_LAUNCHER"] = sys.executable
    return subprocess.run(
        ["/bin/bash", str(HOOKS / name)],
        cwd=ROOT,
        env=env,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _events(project_dir: Path) -> list[dict[str, object]]:
    path = project_dir / EVIDENCE
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("trigger", ["manual", "auto"])
def test_should_checkpoint_curated_handoff_once_when_precompact_runs(
    tmp_path: Path, trigger: str
) -> None:
    project = tmp_path / "project with spaces"
    handoff = project / "tasks" / "handoffs" / "session-handoff-LATEST.md"
    handoff.parent.mkdir(parents=True)
    curated = (
        "# Session Handoff — Current\n\n"
        "## Decisions\n\n- Preserve this exact curated decision.\n"
    )
    handoff.write_text(curated, encoding="utf-8")

    first = _run_hook("pre-compact.sh", project, {"trigger": trigger})
    second = _run_hook("pre-compact.sh", project, {"trigger": trigger})

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    body = handoff.read_text(encoding="utf-8")
    assert curated in body
    assert body.count("<!-- mir:runtime-snapshot:begin -->") == 1
    assert body.count("<!-- mir:runtime-snapshot:end -->") == 1
    assert [event["name"] for event in _events(project)] == [
        "pre-compact",
        "pre-compact",
    ]


def test_should_include_ordered_incomplete_plan_cursors_in_precompact_snapshot(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    handoff = project / "tasks" / "handoffs" / "session-handoff-LATEST.md"
    handoff.parent.mkdir(parents=True)
    (project / "tasks" / "plan.md").write_text(
        "# Plan\n\n"
        "- [ ] Preserve the markdown task order.\n"
        "Step 2: pending | validate the portable hook contract\n"
        "Step 3: blocked | wait for the dependency\n"
        "Step 4: complete | omit this completed step\n",
        encoding="utf-8",
    )

    completed = _run_hook("pre-compact.sh", project, {"trigger": "auto"})

    assert completed.returncode == 0, completed.stderr
    snapshot = handoff.read_text(encoding="utf-8")
    active_items = snapshot.split("### Active Plan Items\n", 1)[1].split(
        "\n### Working Tree", 1
    )[0]
    assert active_items.splitlines() == [
        "- Preserve the markdown task order.",
        "- Step 2: pending | validate the portable hook contract",
        "- Step 3: blocked | wait for the dependency",
    ]
    assert "Step 4: complete" not in snapshot
    assert "- No open plan items." not in snapshot


@pytest.mark.parametrize("trigger", ["manual", "auto"])
def test_should_validate_checkpoint_without_blocking_when_postcompact_runs(
    tmp_path: Path, trigger: str
) -> None:
    project = tmp_path / "project with spaces"
    handoff = project / "tasks" / "handoffs" / "session-handoff-LATEST.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "# Session Handoff\n\n"
        "<!-- mir:runtime-snapshot:begin -->\n"
        "## Runtime Snapshot (Generated)\n"
        "<!-- mir:runtime-snapshot:end -->\n",
        encoding="utf-8",
    )

    completed = _run_hook("post-compact.sh", project, {"trigger": trigger})

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert _events(project)[-1]["name"] == "post-compact"


def test_should_emit_structured_fail_open_warning_when_postcompact_is_degraded(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project with spaces"
    project.mkdir()

    completed = _run_hook("post-compact.sh", project, {"trigger": "auto"})

    assert completed.returncode == 0, completed.stderr
    warning = json.loads(completed.stdout)
    assert warning["continue"] is True
    assert "PostCompact degraded" in warning["systemMessage"]
    assert _events(project)[-1]["name"] == "post-compact"


def test_should_inject_bounded_utf8_handoff_only_for_compact_session_start(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project with spaces"
    handoff = project / "tasks" / "handoffs" / "session-handoff-LATEST.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("Résumé context 🚀\n" + "é" * 20_000, encoding="utf-8")

    completed = _run_hook(
        "compact-resume.sh",
        project,
        {"hook_event_name": "SessionStart", "source": "compact"},
    )

    assert completed.returncode == 0, completed.stderr
    payload = completed.stdout.encode("utf-8")
    assert len(payload) <= 8192
    assert "=== MIR COMPACTION RECOVERY CONTEXT ===" in completed.stdout
    assert "Résumé context 🚀" in completed.stdout
    assert "truncated at 8192 bytes" in completed.stdout
    assert _events(project)[-1]["name"] == "compact-resume"

    for source in ("startup", "resume", "clear"):
        skipped = _run_hook(
            "compact-resume.sh",
            project,
            {"hook_event_name": "SessionStart", "source": source},
        )
        assert skipped.returncode == 0, skipped.stderr
        assert skipped.stdout == ""

    assert [event["name"] for event in _events(project)] == ["compact-resume"]


def test_should_render_exact_claude_and_codex_hooks_from_one_definition(
    tmp_path: Path,
) -> None:
    renderer = ROOT / "templates" / "common-harness" / "scripts" / "render-hook-configs.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(renderer),
            "--definition",
            str(ROOT / "config" / "project-hooks.json"),
            "--output-root",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    claude = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    codex = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    assert claude == json.loads((ROOT / ".claude" / "settings.json").read_text())
    assert codex == json.loads((ROOT / ".codex" / "hooks.json").read_text())
    assert set(codex) <= {"description", "hooks"}
    assert isinstance(codex.get("description"), str)
    for runtime in (claude, codex):
        assert "PreCompact" in runtime["hooks"]
        assert "PostCompact" in runtime["hooks"]
        compact_groups = [
            group
            for group in runtime["hooks"]["SessionStart"]
            if group.get("matcher") == "^compact$"
        ]
        assert len(compact_groups) == 1
        assert ".claude/hooks/compact-resume.sh" in compact_groups[0]["hooks"][0][
            "command"
        ]
    assert claude["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"] == 60
    assert codex["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"] == 3


def test_should_reject_boolean_hook_timeouts(tmp_path: Path) -> None:
    renderer = ROOT / "templates" / "common-harness" / "scripts" / "render-hook-configs.py"
    base = json.loads((ROOT / "config" / "project-hooks.json").read_text())

    for field, value in (("timeout", True), ("timeout_overrides", {"codex": False})):
        definition = json.loads(json.dumps(base))
        definition["events"]["SessionEnd"][0]["hooks"][0][field] = value
        definition_path = tmp_path / f"{field}.json"
        definition_path.write_text(json.dumps(definition), encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(renderer),
                "--definition",
                str(definition_path),
                "--output-root",
                str(tmp_path / field),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode == 1
        assert "positive integer" in completed.stdout


def test_should_complete_session_end_within_codex_timeout(tmp_path: Path) -> None:
    project = tmp_path / "project with spaces"
    handoff = project / "tasks" / "handoffs" / "session-handoff-LATEST.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("# Session Handoff\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)

    completed = _run_hook(
        "session-end.sh",
        project,
        {"reason": "other"},
        timeout=3,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout
    assert "<!-- mir:runtime-snapshot:begin -->" in handoff.read_text(encoding="utf-8")


def test_should_execute_rendered_compact_commands_from_nested_git_directory(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project with spaces"
    nested = project / "src" / "nested"
    hook = project / ".claude" / "hooks" / "pre-compact.sh"
    nested.mkdir(parents=True)
    hook.parent.mkdir(parents=True)
    hook.write_text(
        "#!/bin/bash\n"
        "printf '%s\\n' \"${CLAUDE_PROJECT_DIR:-missing}\" >> \"$MIR_TEST_LOG\"\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)

    renderer = ROOT / "templates" / "common-harness" / "scripts" / "render-hook-configs.py"
    subprocess.run(
        [
            sys.executable,
            str(renderer),
            "--definition",
            str(ROOT / "templates/common-harness/harness/project-hooks.json"),
            "--output-root",
            str(project),
        ],
        cwd=ROOT,
        check=True,
    )
    claude = json.loads((project / ".claude/settings.json").read_text())
    codex = json.loads((project / ".codex/hooks.json").read_text())
    commands = (
        claude["hooks"]["PreCompact"][0]["hooks"][0]["command"],
        codex["hooks"]["PreCompact"][0]["hooks"][0]["command"],
    )
    log = project / "hook-invocations.txt"

    for runtime, command in zip(("claude", "codex"), commands, strict=True):
        env = {**os.environ, "MIR_TEST_LOG": str(log)}
        if runtime == "claude":
            env["CLAUDE_PROJECT_DIR"] = str(project)
        else:
            env.pop("CLAUDE_PROJECT_DIR", None)
        completed = subprocess.run(
            ["/bin/bash", "-c", command],
            cwd=nested,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, (command, completed.stdout, completed.stderr)

    assert log.read_text(encoding="utf-8").splitlines() == [str(project), str(project)]
