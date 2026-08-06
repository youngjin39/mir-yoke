from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shell_wrapper_is_thin_and_valid_bash():
    wrapper = ROOT / "setup.sh"
    body = wrapper.read_text(encoding="utf-8")

    assert "uv sync --project" in body
    assert 'mir bootstrap --project-root "$ROOT" "$@"' in body
    assert "memory.db" not in body
    subprocess.run(["bash", "-n", str(wrapper)], check=True)


def test_powershell_wrapper_has_equivalent_coordinator_contract():
    wrapper = ROOT / "setup.ps1"
    body = wrapper.read_text(encoding="utf-8")

    assert "uv sync --project" in body
    assert '"mir", "bootstrap", "--project-root"' in body
    assert "SkipCapabilityActivation" in body
    assert "Finalize" in body
    assert "ArchitectureInitialized" in body
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
