from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".claude" / "hooks"


def _copy_hooks(project: Path) -> Path:
    target = project / ".claude" / "hooks"
    shutil.copytree(HOOKS, target)
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
    for index, path in enumerate(("spec/STATE.md", r"C:\project\spec\STATE.md")):
        project = tmp_path / str(index)
        project.mkdir()
        completed = _run_pretool(
            project,
            {"tool_name": "Write", "tool_input": {"file_path": path}},
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


def test_ready_receipt_releases_normal_mutation(tmp_path: Path) -> None:
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir" / "bootstrap-receipt.json").write_text(
        '{"status":"ready"}\n', encoding="utf-8"
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
