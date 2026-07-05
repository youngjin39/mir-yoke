from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_codex_shim_blocks_raw_exec_and_logs_quoted_caller(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[3]
    shim = repo_root / "scripts" / "codex-shim.sh"
    real_codex = tmp_path / "real-codex.sh"
    events_file = tmp_path / "events.jsonl"

    real_codex.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    real_codex.chmod(0o755)

    env = {
        **os.environ,
        "CODEX_REAL_BIN": str(real_codex),
        "CODEX_EVENTS_FILE": str(events_file),
        "MIR_CODEX_CALLER": 'a"b',
    }
    result = subprocess.run(
        [str(shim), "exec", "noop"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2

    row = json.loads(events_file.read_text(encoding="utf-8").splitlines()[-1])
    assert row["caller"] == 'a"b'
    assert row["exit_code"] == 2
