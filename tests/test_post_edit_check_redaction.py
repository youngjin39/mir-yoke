"""post-edit-check.sh reports debug and credential hits by location only."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "post-edit-check.sh"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="hook requires jq")


@pytest.mark.parametrize(
    ("name", "template"),
    [("tool.py", 'print("{value}")'), ("app.ts", 'console.log("{value}");')],
)
def test_debug_warning_does_not_echo_matched_line(
    tmp_path: Path, name: str, template: str
) -> None:
    value = "sk-" + "synthetic_test_value_" * 2
    target = tmp_path / name
    target.write_text("\n" + template.format(value=value) + "\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(target)}}),
        capture_output=True, text=True, timeout=30, check=False,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
    )

    assert result.returncode == 0, result.stderr
    assert "[WARNING]" in result.stdout and "[CRITICAL]" in result.stdout
    assert value not in result.stdout + result.stderr
