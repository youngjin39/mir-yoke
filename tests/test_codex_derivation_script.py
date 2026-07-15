"""Codex derivative generator regressions."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_generator_skips_non_agent_markdown_and_empty_targets(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["CODEX_DERIVATION_OUTPUT_ROOT"] = str(tmp_path)
    completed = subprocess.run(
        ["/bin/bash", "scripts/generate_codex_derivatives.sh"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads(
        (tmp_path / ".codex-sync" / "manifest.json").read_text(encoding="utf-8")
    )
    mappings = manifest["mappings"]
    assert all(mapping["source"] != ".claude/agents/README.md" for mapping in mappings)
    assert all(target != ".codex/agents/.toml" for item in mappings for target in item["targets"])
    assert "full=12 after consolidation" in manifest["notes"]
