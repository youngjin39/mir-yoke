"""Published methodology contracts for the second 0.13.27 slice."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ("mir-code/testing", "controlled-experiments.md", ("228791f",), (
        "mutable candidate", "immutable evaluator", "unchanged baseline", "hardware",
        "overhead", "hypothesis", "crashes", "complexity", "finite", "Main",
    )),
    ("mir-core/efficiency", "instruction-change-evaluation.md", ("0d30a6d", "82ac6a7"), (
        "repeated runs", "isolation", "recurring input", "cache", "accepted result",
        "words", "tokens", "retained facts", "corrections", "completeness",
        "negative", "tool schema", "load frequency", "uncertainty", "cold", "warm",
        "always needed", "task-conditional", "historical", "governance",
    )),
    ("mir-core/governance", "skill-patch-from-traces.md", ("84b36cd",), (
        "redacted traces", "one-off", "canonical", "edit budget", "empty proposal",
        "selection", "final evaluation", "regressed", "stable", "instruction length",
        "staged", "rejected", "generation", "hard gate",
    )),
    ("mir-core/memory-evaluation", None, ("2cc8c54",), (
        "owner requests", "frozen source history", "static recall", "dynamic tracking",
        "workflow knowledge", "environment gotchas", "premise awareness", "changed facts",
        "misleading premises", "synthetic", "category labels", "source spans", "no-memory",
        "reader settings", "context limits", "evidence support", "query latency",
        "trade-offs", "unevaluated", "hard gate", "insertion", "live replay",
    )),
)


@pytest.mark.parametrize("target,reference,pins,terms", CASES)
def test_should_publish_bounded_methodology_with_provenance(target, reference, pins, terms):
    plugin, skill = target.split("/")
    root = ROOT / "plugins" / plugin / "skills" / skill
    path = root / "references" / reference if reference else root / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    for pin in pins:
        assert re.search(rf"Inspired by .+ at {pin}", text)
    for term in terms:
        assert term.lower() in " ".join(text.lower().split()), term
    assert len(text.splitlines()) < 60
    if reference:
        entrypoint = (root / "SKILL.md").read_text(encoding="utf-8")
        assert f"](references/{reference})" in entrypoint
        for link in re.findall(r"\]\((references/[^)]+)\)", entrypoint):
            assert (root / link).is_file(), link
    else:
        description = text.split("---")[1]
        assert "only when the owner requests" in description
        assert "name: memory-evaluation" in description
