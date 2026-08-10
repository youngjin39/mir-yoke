from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/loop_driver.sh", scripts / "loop_driver.sh")
    mir = scripts / "mir.sh"
    mir.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1 $2\" = \"loop next\" ]; then printf '{\"status\":\"COMPLETE\"}\\n'; fi\n",
        encoding="utf-8",
    )
    mir.chmod(0o755)
    return project


def test_loop_driver_uses_portable_atomic_directory_lock(tmp_path: Path) -> None:
    project = _project(tmp_path)
    lock = project / "tasks/loop.lock"
    env = os.environ.copy()
    env["MIR_LOOP_LOCK"] = str(lock)

    completed = subprocess.run(
        ["bash", "scripts/loop_driver.sh"],
        cwd=project,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert not lock.exists()
    assert "flock" not in (project / "scripts/loop_driver.sh").read_text(encoding="utf-8")


def test_loop_driver_rejects_concurrent_lock_holder(tmp_path: Path) -> None:
    project = _project(tmp_path)
    lock = project / "tasks/loop.lock"
    lock.mkdir(parents=True)
    (lock / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    env = os.environ.copy()
    env["MIR_LOOP_LOCK"] = str(lock)

    completed = subprocess.run(
        ["bash", "scripts/loop_driver.sh"],
        cwd=project,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "another loop driver holds" in completed.stderr
    assert lock.is_dir()


def test_loop_driver_reclaims_lock_from_dead_holder(tmp_path: Path) -> None:
    project = _project(tmp_path)
    lock = project / "tasks/loop.lock"
    lock.mkdir(parents=True)
    (lock / "pid").write_text("999999999\n", encoding="utf-8")
    env = os.environ.copy()
    env["MIR_LOOP_LOCK"] = str(lock)

    completed = subprocess.run(
        ["bash", "scripts/loop_driver.sh"],
        cwd=project,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert not lock.exists()
