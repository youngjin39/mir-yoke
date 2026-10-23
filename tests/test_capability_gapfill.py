"""Guidance-only gap fills: published content, provenance and resolvable routing."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ("mir-core/design", "frontier-interview.md", "mattpocock/skills at 5beb35b", (
        "consequential", "owner-requested", "Grill-style elicit", "Derive-first",
        "design tree", "prerequisites", "whole frontier", "numbered", "recommended answer",
        '"yes"', "recompute", "frontier is empty", "look up", "already-available",
        "independent questions", "confirmation", "never interactive pickers",
    )),
    ("mir-core/design", "interview-fallback.md", "ADR-58 item 4", (
        "no reply channel", "tool failure", "time-out", "text-only", "unresolved decisions",
        "recommended defaults", "blocked", "next human action", "never invent answers",
    )),
    ("mir-code/bluebricks", "sufficient-solution.md", "DietrichGebert/ponytail at 09c434a", (
        "installed dependency", "one-liner or adapter", "custom code", "security",
        "data-loss", "accessibility", "explicit requirements", "18-23",
    )),
    ("mir-code/code-review", "repository-audit-and-debt.md",
     "DietrichGebert/ponytail at 09c434a", (
         "whole-repository", "concrete failure", "ranked findings", "load assumptions",
         "not checked", "hot-path", "shortcut:", "ceiling", "upgrade trigger",
         "existing evidence or debt record", "missing-trigger", "manual",
     )),
    ("mir-core/automation", "spinning-report.md", "ADR-58 item 5b", (
        "report-only", "SPINNING", "declared number of attempts", "error_sig",
        "identical failure signatures", "no measurable progress", "Main",
        "no automatic retry", "escalation", "actuation",
    )),
    ("mir-core/verify", "three-document-fidelity.md", "fn-opt/dryforge at f5aa6d7", (
        "consequential", "already has", "handoff", "spec", "plan", "intent preservation",
        "spec-over-plan", "requirements to plan steps", "non-reconstructible intent",
        "fresh reviewer", "advisory evidence", "not require", "never an LLM acceptance gate",
    )),
    ("mir-code/code-review", "advisory-consensus.md", "ADR-58 item 1", (
        "disputed high-impact", "advocate", "adversarial reviewer", "judge",
        "existing reviewers", "no new packaged agents", "advisory",
        "deterministic checks", "only hard blockers",
    )),
)


@pytest.mark.parametrize("target,reference,provenance,terms", CASES)
def test_gapfill_reference_content_and_pointer(target, reference, provenance, terms):
    plugin, skill = target.split("/")
    root = ROOT / "plugins" / plugin / "skills" / skill
    path = root / "references" / reference
    text = path.read_text(encoding="utf-8")
    assert f"Inspired by {provenance}." in text
    normalized = " ".join(text.lower().split())
    for term in terms:
        assert term.lower() in normalized, term
    assert len(text.splitlines()) < 50
    entrypoint = (root / "SKILL.md").read_text(encoding="utf-8")
    assert f"](references/{reference})" in entrypoint
    for link in re.findall(r"\]\((references/[^)]+)\)", entrypoint):
        assert (root / link).is_file(), link
