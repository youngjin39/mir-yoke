"""Full manifest provider compared with immutable Python reference records."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/runtime_manifest_e02a"
SPEC = importlib.util.spec_from_file_location("e02a_capture", FIXTURE / "capture.py")
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


@pytest.fixture(scope="module")
def binary():
    override = os.environ.get("MIR_E02A_BINARY")
    if override:
        return Path(override)
    subprocess.run(
        ["cargo", "build", "--offline", "--locked", "--bin", "runtime-manifest"],
        cwd=ROOT / "native/handoff-packet",
        check=True,
    )
    return ROOT / "native/handoff-packet/target/debug/runtime-manifest"


@pytest.mark.parametrize("case", capture.CASES)
def test_create_frozen(binary, case):
    import tempfile

    with tempfile.TemporaryDirectory(prefix="e02a-test-", dir=os.environ["TMPDIR"]) as tmp:
        base = Path(tmp)
        root = base / "runtime"
        manifest = capture.setup(root, case)
        result = capture.record(
            [str(binary)],
            root,
            manifest,
            dict(os.environ, HOME=str(base), PYTHONDONTWRITEBYTECODE="1"),
        )
        expected = json.loads((FIXTURE / "records.json").read_text())["records"][case]
        assert result == expected
