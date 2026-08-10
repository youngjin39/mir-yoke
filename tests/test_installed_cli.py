from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# @spec FR-001 FR-004
def test_should_run_copied_tool_when_repository_python_is_not_on_path(tmp_path: Path) -> None:
    tool_dir = tmp_path / "tools"
    bin_dir = tmp_path / "bin"
    env = os.environ.copy()
    env.update(
        {
            "UV_CACHE_DIR": str(tmp_path / "uv-cache"),
            "UV_TOOL_DIR": str(tool_dir),
            "UV_TOOL_BIN_DIR": str(bin_dir),
        }
    )

    installed = subprocess.run(
        ["uv", "tool", "install", "--force", "--link-mode", "copy", str(ROOT)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert installed.returncode == 0, installed.stderr

    cli = bin_dir / ("mir.exe" if os.name == "nt" else "mir")
    if os.name != "nt":
        assert cli.is_symlink()
        assert cli.resolve().is_relative_to(tool_dir)
    clean_env = env.copy()
    for name in ("PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        clean_env.pop(name, None)
    for args in (
        ["--help"],
        ["bootstrap", "--help"],
        ["capability", "--help"],
        ["executor", "--help"],
        ["loop", "--help"],
        ["policy", "--help"],
        ["run-python", "--help"],
        ["runtime-manifest", "--help"],
    ):
        completed = subprocess.run(
            [str(cli), *args],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
            env=clean_env,
        )
        assert completed.returncode == 0, completed.stderr

    command_probe = subprocess.run(
        [
            str(cli),
            "run-python",
            "--project-root",
            str(tmp_path),
            "--",
            "-c",
            "from pathlib import Path; Path('command-probe.txt').write_text('ready')",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert command_probe.returncode == 0, command_probe.stderr
    assert (tmp_path / "command-probe.txt").read_text(encoding="utf-8") == "ready"

    stdin_probe = subprocess.run(
        [str(cli), "run-python", "--project-root", str(tmp_path), "--", "-"],
        cwd=tmp_path,
        input="print('stdin-ready')\n",
        check=False,
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert stdin_probe.returncode == 0, stdin_probe.stderr
    assert stdin_probe.stdout.strip() == "stdin-ready"

    resource_probe = subprocess.run(
        [
            str(cli),
            "run-python",
            "--project-root",
            str(ROOT),
            "--",
            "-c",
            (
                "from pathlib import Path; "
                "from mir.cli.bootstrap_adoption import _validate_canonical_applied_helper; "
                "errors, _ = _validate_canonical_applied_helper("
                "Path('.'), '.claude/hooks/_lib/run-python.sh', label='installed'); "
                "assert not errors, errors"
            ),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert resource_probe.returncode == 0, resource_probe.stderr
