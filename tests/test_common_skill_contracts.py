"""Portable common-skill contracts owned by the Mir Yoke provider."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent
DESIGN_SKILL = ROOT / "plugins" / "mir-core" / "skills" / "design" / "SKILL.md"
SPEC_SKILL = ROOT / "plugins" / "mir-core" / "skills" / "spec-architect"


def _read_spec(relative: str) -> str:
    return (SPEC_SKILL / relative).read_text(encoding="utf-8")


def test_design_declares_proportional_intent_extraction() -> None:
    text = DESIGN_SKILL.read_text(encoding="utf-8")

    for marker in ("Intent Extraction", "Materials", "Decision Surface", "migration"):
        assert marker in text, f"design skill is missing intent marker: {marker}"
    assert "skip the separate design artifact" in text
    assert "Use only the design, parallel analysis, or independent review needed" in text


def test_spec_architect_delegates_elicitation_to_design() -> None:
    completeness = _read_spec("references/00-completeness.md")

    assert "Intent Extraction section" in completeness
    assert "does not define its own questioning protocol" in completeness
    assert "X-17" in _read_spec("SKILL.md")


def test_spec_architect_does_not_redefine_remote_question_protocol() -> None:
    assert "AskUserQuestion" not in _read_spec("references/00-completeness.md")


def test_spec_relations_exist_only_in_the_graph() -> None:
    skill_files = (
        "SKILL.md",
        "references/00-completeness.md",
        "references/01-methodology.md",
        "references/02-ai-ready-gate.md",
        "references/03-reverse-recovery.md",
        "references/04-artifacts.md",
        "references/05-views.md",
    )
    retired_fields = ("traces_to", "allocated_to", "code_paths", "quality_links")

    assert "graph.yaml" in _read_spec("references/04-artifacts.md")
    for relative in skill_files:
        text = _read_spec(relative)
        for field in retired_fields:
            assert field not in text, f"{relative} names retired relation field {field}"


def test_spec_feature_attributes_have_a_storage_file() -> None:
    artifacts = _read_spec("references/04-artifacts.md")

    assert "feat/<FEAT-id>.yaml" in artifacts
    assert "coverage:" in artifacts


def test_spec_completeness_uses_derive_first() -> None:
    completeness = _read_spec("references/00-completeness.md")

    assert "derived" in completeness
    assert "Question count is not a quality metric" in completeness


def test_spec_orphan_check_distinguishes_attachment_nodes() -> None:
    artifacts = _read_spec("references/04-artifacts.md")

    assert "Body nodes and attachment nodes" in artifacts
    assert "orphan check" in artifacts
    assert "zero orphaned **body** nodes" in _read_spec("SKILL.md")


def test_spec_coverage_denominator_is_defined() -> None:
    completeness = _read_spec("references/00-completeness.md")

    assert "The unit of a cell" in completeness
    for rule in ("use case count x 7", "always 9", "always 10"):
        assert rule in completeness, f"missing denominator rule: {rule}"


def test_spec_gaps_to_graph_mapping_is_defined() -> None:
    artifacts = _read_spec("references/04-artifacts.md")

    assert "`gaps.yaml` items and the graph" in artifacts
    assert "No edge" in artifacts
