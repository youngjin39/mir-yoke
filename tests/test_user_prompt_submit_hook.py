"""Advisory behavior for the repository-owned prompt hook."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude/hooks/user-prompt-submit.sh"


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
