"""Public bootstrap emits the compact, safety-complete repository profile."""

import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_setup_profile_tracks_canonical_and_generated_surfaces(tmp_path: Path) -> None:
    shutil.copy2(ROOT / "setup.sh", tmp_path / "setup.sh")

    completed = subprocess.run(
        ["/bin/bash", "setup.sh"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    profile = tomllib.loads(
        (tmp_path / ".mir" / "repo-profile.toml").read_text(encoding="utf-8")
    )
    assert ".mir/memory.db*" in profile["paths"]["protected_paths"]
    assert "**/AGENTS.md" in profile["paths"]["generated_paths"]
    assert ".codex/**" in profile["paths"]["generated_paths"]
    assert profile["preserve"]["agent_memory_paths"] == [".mir/memory.db"]
    assert "scripts/verify_codex_sync.py" in profile["paths"]["verification_paths"]
