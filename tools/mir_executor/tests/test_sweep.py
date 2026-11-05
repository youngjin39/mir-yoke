"""Native sweep comparisons against independently frozen Python results and effects."""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import pathlib
import subprocess

import pytest

from tools.mir_executor.jobs import JobRecord, JobRegistry

ROOT = pathlib.Path(__file__).resolve().parents[3]
CRATE = ROOT / "native/handoff-packet"
CORPUS = json.loads((CRATE / "tests/fixtures/g6/sweep.json").read_text())
_spec = importlib.util.spec_from_file_location(
    "sweep_fixture", CRATE / "tests/fixtures/generate_executor_sweep.py"
)
assert _spec is not None and _spec.loader is not None
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)


@pytest.fixture(scope="module")
def native_sweep() -> pathlib.Path:
    target = pathlib.Path(os.environ.get("CARGO_TARGET_DIR", CRATE / "target"))
    subprocess.run(
        ["cargo", "build", "--manifest-path", str(CRATE / "Cargo.toml"),
         "--locked", "--bin", "executor-query"],
        check=True, capture_output=True,
    )
    return target / "debug" / ("executor-query.exe" if os.name == "nt" else "executor-query")


def test_find_stale_uses_strict_timeout_boundary(tmp_path: pathlib.Path) -> None:
    started = datetime.datetime(2026, 7, 11, tzinfo=datetime.UTC)
    registry = JobRegistry(tmp_path / "jobs.db")
    try:
        registry.insert(JobRecord(
            job_id="boundary", change_id="sweep-test", category="unit", family=None,
            repo_root=str(tmp_path), codex_args=[], timeout_seconds=60,
            status="running", started_at=started.isoformat(),
        ))
        assert registry.find_stale(started + datetime.timedelta(seconds=179), 120) == []
        assert [job.job_id for job in registry.find_stale(
            started + datetime.timedelta(seconds=181), 120
        )] == ["boundary"]
    finally:
        registry.close()


@pytest.mark.parametrize("apply", [False, True])
def test_native_cli_matches_frozen_results_and_durable_effects(
    tmp_path: pathlib.Path, native_sweep: pathlib.Path, apply: bool
) -> None:
    fixture.setup(tmp_path, "artifact")
    before = fixture.snapshot(tmp_path, raw=True)
    command = [str(native_sweep), "--home-root", str(tmp_path / "repo"),
               "sweep", "--jobs-db", str(tmp_path / "jobs.db")]
    if apply:
        command.append("--apply")
    result = subprocess.run(command, cwd=tmp_path / "repo", capture_output=True)
    expected = CORPUS["cli"][str(apply).lower()]
    assert result.returncode == expected["status"], result.stderr.decode()
    assert result.stderr == expected["stderr"].encode()
    escaped_root = str(tmp_path).replace("\\", "\\\\").encode()
    assert result.stdout.replace(escaped_root, b"$ROOT") == expected["stdout"].encode()
    assert len(result.stdout.splitlines()) == 1
    assert fixture.normalize(json.loads(result.stdout), tmp_path) == expected["result"]
    state = fixture.snapshot(tmp_path)
    for row in state["rows"].get("artifact_sweeps", []):
        row["swept_at"] = "$NOW"
    assert state == expected["state"]
    if not apply:
        assert fixture.snapshot(tmp_path, raw=True) == before
