from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_codex_shim_json_escapes_quoted_caller(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[3]
    shim = repo_root / "scripts" / "codex-shim.sh"
    real_codex = tmp_path / "real-codex.sh"
    events_file = tmp_path / "events.jsonl"
    invoked_file = tmp_path / "invoked"

    real_codex.write_text(
        "#!/usr/bin/env sh\nprintf '%s\\n' \"$@\" > \"$STUB_ARGS_FILE\"\n",
        encoding="utf-8",
    )
    real_codex.chmod(0o755)

    env = {
        **os.environ,
        "CODEX_REAL_BIN": str(real_codex),
        "CODEX_EVENTS_FILE": str(events_file),
        "MIR_CODEX_CALLER": 'a"b',
        "STUB_ARGS_FILE": str(invoked_file),
    }
    subprocess.run(
        [str(shim), "mcp-server"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    row = json.loads(events_file.read_text(encoding="utf-8").splitlines()[-1])
    assert row["caller"] == 'a"b'
    assert invoked_file.read_text(encoding="utf-8").splitlines() == ["mcp-server"]
