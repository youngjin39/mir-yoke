"""Test hook executability, syntax, and narrow raw-Codex command screening."""
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_all_hooks_executable():
    hooks_dir = Path(".claude/hooks")
    if not hooks_dir.exists():
        return  # No hooks directory yet — pass until baseline is established
    hooks = list(hooks_dir.glob("*.sh"))
    if not hooks:
        return  # No hooks present yet
    for hook in hooks:
        mode = hook.stat().st_mode
        assert mode & stat.S_IXUSR, f"{hook} not executable (missing +x)"
        result = subprocess.run(
            ["bash", "-n", str(hook)],
            capture_output=True,
        )
        assert result.returncode == 0, (
            f"{hook} bash syntax error: {result.stderr.decode()}"
        )


def _run_pre_tool_use(
    command: str, project_dir: Path
) -> subprocess.CompletedProcess[str]:
    script = ROOT / ".claude" / "hooks" / "pre-tool-use.sh"
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return subprocess.run(
        ["/bin/bash", str(script)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
    )


@pytest.mark.parametrize(
    "command",
    [
        "codex exec --cd /tmp/x",
        "codex e --cd /tmp/x",
        "echo prompt | codex exec --cd /tmp/x",
        "/usr/local/bin/codex exec --cd /tmp/x",
        "codex --model gpt-5 exec --cd /tmp/x",
        "env MIR_TEST=1 codex exec --cd /tmp/x",
        "/usr/bin/env -- codex e --cd /tmp/x",
    ],
)
def test_pre_tool_use_blocks_direct_raw_codex_exec(
    command: str, tmp_path: Path
) -> None:
    result = _run_pre_tool_use(command, tmp_path)

    assert result.returncode == 2
    assert "raw codex exec/e is banned" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "python3 -c 'print(\"codex exec\")'",
        "echo codex exec",
        "git grep 'codex exec'",
        "rg -n 'safe|codex exec|other' docs",
        "rg -n codex exec docs",
        "printf '%s' 'codex exec'",
        "# codex exec --help",
    ],
)
def test_pre_tool_use_allows_raw_codex_text_outside_command_position(
    command: str, tmp_path: Path
) -> None:
    result = _run_pre_tool_use(command, tmp_path)

    assert result.returncode == 0


if __name__ == "__main__":
    test_all_hooks_executable()
    print("test_hook_executability: PASS")
