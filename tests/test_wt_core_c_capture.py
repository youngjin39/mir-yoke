"""The offline PC oracle captures every B15 route without compacting file bytes."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "tests/fixtures/wt_core_c/capture_windows.py"
PIN = "aa4fdbdbaa1c9641d5b7594e6c73174a0e0e4315"


@unittest.skipUnless(os.name == "posix", "Unix frozen verification; PC capture runs separately")
def test_all_b15_routes(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
           "PYTHONDONTWRITEBYTECODE": "1"}
    bundle, output = tmp_path / "bundle", tmp_path / "records.json"
    commands = [
        ["--prepare", "--repo", str(ROOT), "--yaml-root", str(Path(yaml.__file__).parent)],
        ["--scratch", str(tmp_path / "capture"), "--output", str(output), "--check-unix"],
    ]
    for args in commands:
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-X", "utf8", str(CAPTURE),
             "--bundle", str(bundle), *args],
            cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
    records = json.loads(output.read_text())["b15"]
    frozen = json.loads((bundle / PIN /
                        "native/handoff-packet/tests/fixtures/w2/b15-render.json").read_text())
    assert len(records) == 53, f"captured {len(records)} of 53 B15 scenarios"
    assert records.keys() == frozen.keys()
    for name, record in records.items():
        assert set(record) == {"observation", "file_hex", "byte_length", "sha256",
                               "character_length"}, name
        if record["file_hex"] is None:
            assert all(record[field] is None for field in
                       ("byte_length", "sha256", "character_length")), name
        else:
            raw = bytes.fromhex(record["file_hex"])
            assert len(raw) == record["byte_length"], name
            assert hashlib.sha256(raw).hexdigest() == record["sha256"], name
            assert len(raw.decode("utf-8")) == record["character_length"], name
    assert records["cli.in_place"]["file_hex"] is not None
    assert records["cli.None.False.False"]["observation"]["value"]["results"] == [{"value": 0}]
    assert records["cli.invalid_target"]["observation"]["value"]["results"] == [
        {"error": ["SystemExit", "2"]}]
