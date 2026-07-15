"""Codex derivative generator regressions."""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
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

    claude_text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert claude_text in agents_text
    assert "## Codex closeout delta" in agents_text
    assert "- Skills: `" not in agents_text
    assert "adopt it as your session contract" not in agents_text
    assert "## Codex Hook-Mirror Obligations" not in agents_text
    assert len(claude_text.splitlines()) <= 80
    assert len(agents_text.splitlines()) <= 90

    budgets = {
        entry["path"]: entry
        for entry in json.loads(
            (ROOT / "config" / "doc-size-guard.json").read_text(encoding="utf-8")
        )
    }
    assert len(claude_text.splitlines()) <= budgets["CLAUDE.md"]["max_lines"]
    assert len(agents_text.splitlines()) <= budgets["AGENTS.md"]["max_lines"]

    skill_mappings = [
        mapping
        for mapping in mappings
        if mapping["source"].startswith(".claude/skills/")
    ]
    assert len(skill_mappings) == 12
    for mapping in skill_mappings:
        skill_name = Path(mapping["source"]).name
        assert mapping["targets"] == [f".agents/skills/{skill_name}"]
        target = tmp_path / mapping["targets"][0]
        assert target.is_symlink()
        assert target.readlink() == Path(f"../../.claude/skills/{skill_name}")
        staging_target = tmp_path / ".codex-sync" / "staging" / mapping["targets"][0]
        assert staging_target.is_symlink()
        assert staging_target.readlink() == Path(f"../../../../.claude/skills/{skill_name}")

    preserve = tomllib.loads((ROOT / ".mir-preserve.toml").read_text(encoding="utf-8"))
    for heading in preserve["claude_md_preserve"]["sections"]:
        assert heading in claude_text
