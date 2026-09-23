"""Advisory behavior for the repository-owned prompt hook."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude/hooks/user-prompt-submit.sh"


@pytest.mark.parametrize(
    ("prompt", "expected", "warning"),
    [
        (
            "Please inspect compact lifecycle advisory warning behavior today",
            '[context-pull] Candidate retrieval: scripts/mir.sh context pull '
            '"please inspect compact lifecycle advisory warning"\n',
            "",
        ),
        ("short prompt", "", ""),
        ("  /review " + "context " * 8, "", ""),
        ("  <task-notification>" + "context " * 8, "", ""),
        (None, "", "Invalid prompt payload"),
    ],
)
def test_should_inject_advisory_without_blocking_when_codex_submits_prompt(
    tmp_path: Path, prompt: str | None, expected: str, warning: str
) -> None:
    rendered = subprocess.run(
        [
            sys.executable,
            str(ROOT / "templates/common-harness/scripts/render-hook-configs.py"),
            "--definition", str(ROOT / "config/project-hooks.json"),
            "--output-root", str(tmp_path),
        ],
        capture_output=True, text=True, check=False,
    )
    assert rendered.returncode == 0, rendered.stderr
    codex = json.loads((tmp_path / ".codex/hooks.json").read_text())
    assert "StopFailure" not in codex["hooks"]
    hook = codex["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    payload = {
        "session_id": "parity-test", "transcript_path": None,
        "cwd": str(ROOT), "hook_event_name": "UserPromptSubmit",
        "model": "test-model", "permission_mode": "dontAsk",
        "turn_id": "parity-turn", "prompt": prompt,
    }
    completed = subprocess.run(
        ["bash", "-c", hook["command"]], cwd=ROOT,
        input=json.dumps(payload), capture_output=True, text=True,
        check=False, timeout=hook["timeout"],
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == expected
    if warning:
        assert warning in completed.stderr
    else:
        assert completed.stderr == ""


@pytest.mark.parametrize(
    ("payload", "launcher_body", "warning"),
    [
        ('{"prompt": "private-marker",', None, "Invalid prompt payload"),
        (
            '{"prompt": "private-marker: a sufficiently long prompt for interpreter testing"}',
            "#!/bin/bash\nexit 127\n",
            "Invalid prompt payload or Python unavailable",
        ),
        (
            '{"prompt": "private-marker: a sufficiently long prompt for tokenizer testing"}',
            "#!/bin/bash\n"
            'case "$*" in *STOPWORDS*) exit 7 ;; esac\n'
            'exec "$MIR_TEST_PYTHON" "$@"\n',
            "Prompt tokenization unavailable",
        ),
    ],
)
def test_should_warn_without_prompt_leak_when_advisory_processing_fails(
    tmp_path: Path, payload: str, launcher_body: str | None, warning: str
) -> None:
    hooks = tmp_path / ".claude/hooks"
    (hooks / "_lib").mkdir(parents=True)
    shutil.copy2(HOOK, hooks / HOOK.name)
    launcher = hooks / "_lib/run-python.sh"
    launcher.write_text(
        launcher_body or "#!/bin/bash\nexec \"$MIR_TEST_PYTHON\" \"$@\"\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    env = {**os.environ, "MIR_TEST_PYTHON": sys.executable}

    completed = subprocess.run(
        ["bash", str(hooks / HOOK.name)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert completed.returncode == 0
    assert warning in completed.stderr
    assert completed.stdout == ""
    assert "private-marker" not in completed.stderr
    assert "Traceback" not in completed.stderr


def test_should_keep_context_pull_command_for_valid_prompt(tmp_path: Path) -> None:
    hooks = tmp_path / ".claude/hooks"
    (hooks / "_lib").mkdir(parents=True)
    shutil.copy2(HOOK, hooks / HOOK.name)
    launcher = hooks / "_lib/run-python.sh"
    launcher.write_text('#!/bin/bash\nexec "$MIR_TEST_PYTHON" "$@"\n', encoding="utf-8")
    launcher.chmod(0o755)

    completed = subprocess.run(
        ["bash", str(hooks / HOOK.name)],
        input='{"prompt": "Please inspect compact lifecycle advisory warning behavior today"}',
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "MIR_TEST_PYTHON": sys.executable},
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert completed.stdout.startswith(
        '[context-pull] Candidate retrieval: scripts/mir.sh context pull "'
    )
