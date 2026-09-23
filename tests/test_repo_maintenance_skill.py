"""Contract for the portable repository-maintenance checklist skill."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "mir-core" / "skills" / "repo-maintenance" / "SKILL.md"


def test_repo_maintenance_skill_keeps_the_twenty_item_checklist() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert re.search(r"^name: repo-maintenance$", text, re.MULTILINE)
    checklist = text.split("## Checklist", 1)[1].split("## Workflow", 1)[0]
    numbers = [int(match) for match in re.findall(r"^(\d+)\. ", checklist, re.MULTILINE)]
    assert numbers == list(range(1, 21))


def test_repo_maintenance_skill_never_fabricates_provenance_or_weakens_guards() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "Never fabricate provenance" in text
    assert "never weakens a safety guard" in text
    assert "Never delete a rule, decision or lesson" in text
