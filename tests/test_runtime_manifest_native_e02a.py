"""Full manifest provider compared with immutable Python reference records."""

import importlib.util
import json
import os
from pathlib import Path

import pytest
from e02a_binary import binary as e02a_binary

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/runtime_manifest_e02a"
SPEC = importlib.util.spec_from_file_location("e02a_capture", FIXTURE / "capture.py")
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


@pytest.fixture(scope="session")
def binary():
    return e02a_binary("runtime-manifest", "MIR_E02A_BINARY")


@pytest.mark.parametrize("case", capture.CASES)
def test_create_frozen(binary, case):
    import tempfile

    with tempfile.TemporaryDirectory(prefix="e02a-test-") as tmp:
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
