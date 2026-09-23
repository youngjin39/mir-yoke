"""Contract for the portable repository-maintenance checklist skill."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "mir-core" / "skills" / "repo-maintenance" / "SKILL.md"


def test_repo_maintenance_skill_keeps_the_twenty_one_item_checklist() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert re.search(r"^name: repo-maintenance$", text, re.MULTILINE)
    checklist = text.split("## Checklist", 1)[1].split("## Workflow", 1)[0]
    numbers = [int(match) for match in re.findall(r"^(\d+)\. ", checklist, re.MULTILINE)]
    assert numbers == list(range(1, 22))
    assert "twenty-one fixed items" in text.split("\n---", 1)[0]


def test_repo_maintenance_skill_never_fabricates_provenance_or_weakens_guards() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "Never fabricate provenance" in text
    assert "never weakens a safety guard" in text
    assert "Never delete a rule, decision or lesson" in text


def test_should_require_documented_memory_repairs_when_defects_are_found() -> None:
    text = SKILL.read_text(encoding="utf-8")
    memory = re.search(r"^6\. (.+)$", text, re.MULTILINE).group(1)
    for requirement in (
        "inspect and repair",
        "documented commands",
        "stable snapshot",
        "WAL",
        "open connections",
        "stale or missing-source records",
        "relation-graph defects",
    ):
        assert requirement in memory


def test_should_name_both_harnesses_and_preserve_allowed_runtime_behavior() -> None:
    text = SKILL.read_text(encoding="utf-8")
    harness = re.search(r"^7\. (.+)$", text, re.MULTILINE).group(1)
    assert "Claude/Codex" in harness
    bounds = text.split("## Bounds", 1)[1].split("## Checklist", 1)[0]
    for requirement in (
        "non-blocking context or logging",
        "remove leftovers",
        "Never add restrictions",
        "recreate owner-removed hooks",
        "block previously allowed behavior",
    ):
        assert requirement in bounds


@pytest.mark.parametrize(
    "requirements",
    [
        (
            "either Claude CLI or Codex CLI is Main",
            "current rules",
            "design records",
            "user intent",
        ),
        ("CLAUDE.md", "generated AGENTS.md", "nested", "same rules"),
        ("equivalent hook events and commands", "StopFailure", "Codex-only", "exemptions"),
        ("SessionStart", "same cursor", "intent", "native-memory index"),
        ("skills and workflows load in both",),
        ("MCP bindings match",),
        ("Codex hook trust", "untrusted or modified hooks block Codex-side enforcement"),
        ("synthetic payload", "fresh session observation", "item 19", "Static docs are not proof"),
    ],
)
def test_should_require_checkable_main_runtime_parity_probes(requirements: tuple[str, ...]) -> None:
    text = SKILL.read_text(encoding="utf-8")
    checklist = text.split("## Checklist", 1)[1].split("## Workflow", 1)[0]
    parity = re.search(r"^21\. ([\s\S]+)", checklist, re.MULTILINE)
    assert parity is not None, "Missing item 21: parity when either CLI is Main"
    for requirement in requirements:
        assert requirement in parity.group(1)
