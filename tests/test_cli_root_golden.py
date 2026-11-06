"""Frozen records of the public `mir` CLI root, captured from the unmodified Python reference.

The Python root is the reference until its native replacement switches; a later Rust front
replays the same file.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "native/handoff-packet/tests/fixtures/w2/cli-root.json"
RECORDS = json.loads(FIXTURE.read_text(encoding="utf-8"))
CONSOLE = "from mir.cli.__main__ import main; raise SystemExit(main())"
LAZY = (
    "import sys, mir.cli; print('\\n'.join(sorted(x for x in sys.modules"
    " if x == 'mir' or x.startswith('mir.'))))"
)

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX argv bytes")


def _environment() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}


def _expected(record: dict) -> tuple[int, bytes, bytes]:
    return record["exit"], base64.b64decode(record["stdout"]), base64.b64decode(record["stderr"])


@pytest.mark.parametrize("record", RECORDS, ids=lambda record: record["id"])
def test_python_root_matches_frozen_records(record: dict) -> None:
    args = [base64.b64decode(arg) for arg in record["argv"]]
    heads = {"module": ["-m", "mir"], "console": ["-c", CONSOLE], "import": ["-c", LAZY]}
    result = subprocess.run([sys.executable, *heads[record["entry"]], *args], cwd=ROOT,
                            env=_environment(), capture_output=True, check=False)
    assert (result.returncode, result.stdout, result.stderr) == _expected(record)
