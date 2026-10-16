from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_harness_consistency_zero_error_on_current_repo(tmp_path: Path) -> None:
    manifest = json.loads((ROOT / "config/harness-consistency.json").read_text(encoding="utf-8"))
    for rule in manifest["rules"]:
        if rule["name"] == "generated_marker_rerender":
            rule["enabled"] = False
    manifest_path = tmp_path / "harness-consistency.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    print("R11 generated_marker_rerender skipped: requires the live agent-memory DB")
    proc = subprocess.run(
        [
            sys.executable, "-m", "tools.harness_consistency", "run",
            "--manifest", str(manifest_path), "--format", "json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["overall"] == "pass", result["summary"]
    assert result["summary"]["error"] == 0
