"""Install the Cargo console in a test-local tool directory."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from e02a_binary import binary


@pytest.fixture(scope="session")
def installed_mir(tmp_path_factory) -> Path:
    source = binary("mir", "MIR_F07_Y_BINARY")
    tool_dir = tmp_path_factory.mktemp("mir tool bin")
    filename = "mir.exe" if os.name == "nt" else "mir"
    return Path(shutil.copy2(source, tool_dir / filename))


def run_installed_mir(binary: Path, root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [binary, *args],
        cwd=root,
        env=dict(os.environ, HOME=str(root)),
        capture_output=True,
        timeout=15,
    )
