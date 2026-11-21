"""Startup declines must precede every reference or interpreter effect."""

import json
import shutil
import subprocess

import pytest
from e02a_binary import binary
from run_python_startup_capture import FIXTURE, STARTUP_DIRECTORY, capture, reference, result, setup

RECORDS = json.loads(FIXTURE.read_text())["records"]


def test_startup_reference_regeneration():
    assert capture() == json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: r["name"] + "-" + r["state"])
def test_startup_admission(tmp_path, record):
    tmp_path = tmp_path / STARTUP_DIRECTORY
    env, decline = setup(tmp_path, record["name"], record["state"])
    script = reference(tmp_path)
    shutil.copy2(binary("run-python-launcher", "MIR_RUN_PYTHON_LAUNCHER_BINARY"), script)
    process = subprocess.run(
        [str(script), "-c", "unused"], env=env, cwd=tmp_path,
        capture_output=True, check=False, timeout=10,
    )
    if decline:
        assert (process.returncode, process.stdout, process.stderr) == (64, b"", b"")
        assert not (tmp_path / "effect").exists()
        script.unlink()
        reference(tmp_path)
        process = subprocess.run(
            ["/bin/bash", str(script), "-c", "unused"], env=env, cwd=tmp_path,
            capture_output=True, check=False, timeout=10,
        )
    assert result(process, tmp_path) == record["reference"]
    # pytest's tmp_path is retained by pytest; remove this test's synthetic state.
    shutil.rmtree(tmp_path)
