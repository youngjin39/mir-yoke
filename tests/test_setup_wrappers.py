from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shell_wrapper_is_thin_and_valid_bash():
    wrapper = ROOT / "setup.sh"
    body = wrapper.read_text(encoding="utf-8")

    assert "uv sync --project" in body
    assert 'mir bootstrap --project-root "$ROOT" "$@"' in body
    assert "--storage-root" in body
    assert "UV_CACHE_DIR" in body
    assert "UV_PYTHON_INSTALL_DIR" in body
    assert "UV_TOOL_DIR" in body
    assert "MIR_CAPABILITY_HOME" in body
    assert "memory.db" not in body
    subprocess.run(["bash", "-n", str(wrapper)], check=True)


def test_shell_wrapper_exports_external_storage_before_uv_sync(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s|%s|%s|%s|%s\\n' \"$*\" \"$UV_CACHE_DIR\" "
        "\"$UV_PYTHON_INSTALL_DIR\" \"$UV_TOOL_DIR\" \"$MIR_CAPABILITY_HOME\" "
        '>> \"$UV_TEST_LOG\"\n',
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    storage = tmp_path / "external storage"
    log = tmp_path / "uv.log"
    env = os.environ.copy()
    env.update({"PATH": f"{fake_bin}{os.pathsep}{env['PATH']}", "UV_TEST_LOG": str(log)})

    completed = subprocess.run(
        ["bash", str(ROOT / "setup.sh"), "--storage-root", str(storage), "--json"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    first = log.read_text(encoding="utf-8").splitlines()[0].split("|")
    assert first[0].startswith("sync --project")
    assert first[1:] == [
        str(storage / "uv" / "cache"),
        str(storage / "uv" / "python"),
        str(storage / "uv" / "tools"),
        str(storage / "mir" / "capabilities"),
    ]


def test_powershell_wrapper_has_equivalent_coordinator_contract():
    wrapper = ROOT / "setup.ps1"
    body = wrapper.read_text(encoding="utf-8")

    assert "uv sync --project" in body
    assert '"mir", "bootstrap", "--project-root"' in body
    assert "SkipCapabilityActivation" in body
    assert "Finalize" in body
    assert "ArchitectureInitialized" in body
    assert "StorageRoot" in body
    assert "UV_CACHE_DIR" in body
    assert "UV_PYTHON_INSTALL_DIR" in body
    assert "UV_TOOL_DIR" in body
    assert "MIR_CAPABILITY_HOME" in body
    assert "memory.db" not in body

    pwsh = shutil.which("pwsh")
    if pwsh:
        subprocess.run(
            [
                pwsh,
                "-NoProfile",
                "-Command",
                f"[void][scriptblock]::Create((Get-Content -Raw '{wrapper}'))",
            ],
            check=True,
        )
