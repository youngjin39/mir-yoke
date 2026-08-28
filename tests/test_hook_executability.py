"""Test hook executability, syntax, and narrow raw-Codex command screening."""
import hashlib
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
    command: str,
    project_dir: Path,
    *,
    payload: dict[str, object] | None = None,
) -> subprocess.CompletedProcess[str]:
    script = ROOT / ".claude" / "hooks" / "pre-tool-use.sh"
    manifest = project_dir / "config/bootstrap-adoption.json"
    evidence = project_dir / "spec/bootstrap-evidence.yaml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("verified: true\n", encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "mir_yoke_source_commit": "a" * 40,
                "surfaces": {
                    "bootstrap_start_gate": {
                        "evidence_paths": ["spec/bootstrap-evidence.yaml"]
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (project_dir / ".mir").mkdir(parents=True, exist_ok=True)
    (project_dir / ".mir" / "bootstrap-receipt.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "source": {"mir_yoke_commit": "a" * 40},
                "manifest": {
                    "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()
                },
                "evidence": [
                    {
                        "path": "spec/bootstrap-evidence.yaml",
                        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return subprocess.run(
        ["/bin/bash", str(script)],
        input=json.dumps(
            payload or {"tool_name": "Bash", "tool_input": {"command": command}}
        ),
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


def test_pre_tool_use_blocks_secret_path_from_codex_apply_patch_command(
    tmp_path: Path,
) -> None:
    patch = """*** Begin Patch
*** Update File: .env
@@
-OLD=value
+NEW=value
*** End Patch
"""

    result = _run_pre_tool_use(
        "",
        tmp_path,
        payload={"tool_name": "apply_patch", "tool_input": {"command": patch}},
    )

    assert result.returncode == 2
    assert "secret or credential file" in result.stderr


def test_post_edit_check_scans_codex_apply_patch_command(tmp_path: Path) -> None:
    path = tmp_path / "docs" / "notes.md"
    path.parent.mkdir(parents=True)
    path.write_text("token=sk-abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: docs/notes.md
*** End Patch
"""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}

    result = subprocess.run(
        ["/bin/bash", str(ROOT / ".claude/hooks/post-edit-check.sh")],
        input=json.dumps(
            {"tool_name": "apply_patch", "tool_input": {"command": patch}}
        ),
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
    )

    assert result.returncode == 0
    assert "Possible credential/API key" in result.stdout
    assert "docs/notes.md" in result.stdout
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in result.stdout


if __name__ == "__main__":
    test_all_hooks_executable()
    print("test_hook_executability: PASS")
