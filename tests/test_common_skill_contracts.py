"""Portable common-skill contracts owned by the Mir Yoke provider."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
DESIGN_SKILL = ROOT / "plugins" / "mir-core" / "skills" / "design" / "SKILL.md"
SPEC_SKILL = ROOT / "plugins" / "mir-core" / "skills" / "spec-architect"


def _read_skill(plugin: str, skill: str) -> str:
    return (ROOT / "plugins" / plugin / "skills" / skill / "SKILL.md").read_text(
        encoding="utf-8"
    )


def _read_spec(relative: str) -> str:
    return (SPEC_SKILL / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "markers",
    [
        ("user-visible or stateful behaviour", "feature, a bug fix", "review or audit"),
        (
            "each existing flow it touches",
            "normal path",
            "failure, retry, cancel",
            "late or out-of-order results",
            "navigation",
            "tab or screen switch",
            "background and resume",
            "update, restart and quit",
            "concurrent or repeated",
            "each shipped platform",
        ),
        (
            "action",
            "expected visible and durable outcome",
            "evidence kind",
            "test through the production route",
            "real-boundary check",
            "execution on the named platform",
        ),
        ("writer receives the rows with the brief", "fails before the change (step 3)"),
        (
            "rows are request-matrix cells (step 4)",
            "without executed evidence",
            "open matrix cell",
            "never a pass",
            "not run on that platform",
        ),
        (
            "reviewer first looks for missing rows",
            "unreachable rows",
            "wrong expected outcome",
            "mocks that disagree with their real producer",
            "test that expects the defective behaviour is not evidence",
        ),
        (
            "concrete input",
            "wrong outcome",
            "requirement it violates",
            "preference is a suggestion",
        ),
        ("fix to a finding gets rows", "reviewed again", "state or asynchronous behaviour"),
        (
            "Documentation, configuration and behaviour-preserving changes",
            "not applicable with a reason",
        ),
    ],
    ids=[
        "applies",
        "flows",
        "row-form",
        "writer",
        "matrix",
        "reviewer",
        "findings",
        "fixes",
        "exemption",
    ],
)
def test_should_preserve_behaviour_scenario_decisions_in_portable_method(
    markers: tuple[str, ...],
) -> None:
    path = (
        ROOT
        / "plugins/mir-lifecycle-hooks/skills/runtime-continuity/references/default-work-method.md"
    )
    text = path.read_text(encoding="utf-8")
    section = text.split("## Behaviour scenarios\n", 1)[1].split("\n## ", 1)[0]
    normalized = " ".join(section.split())
    for marker in markers:
        assert marker in normalized
    rows = {line.split(" | ")[0]: line for line in text.splitlines() if line.startswith("| ")}
    assert "[Behaviour scenarios](#behaviour-scenarios)" in rows["| 2"]
    assert "scenario rows are request-matrix cells" in rows["| 4"]
    assert "guidance, not a gate" in " ".join(text.split())
    assert "adds no hook, blocking check, agent or review count" in normalized


@pytest.mark.parametrize(
    "markers",
    [
        ("each row", "test through the production route", "named platform check"),
        ("visible and durable outcome", "opposite or neighbouring state"),
        ("controlled completion order", "async rows"),
        ("real-boundary check", "producer is mocked"),
        (
            "not executed at its boundary stays open",
            "reported",
            "expects the reported defect",
            "not regression evidence",
        ),
    ],
    ids=["routes", "outcomes", "async", "producer", "open-and-defect"],
)
def test_should_map_behaviour_scenarios_to_executed_testing_boundaries(
    markers: tuple[str, ...],
) -> None:
    text = " ".join(_read_skill("mir-code", "testing").split())
    for marker in markers:
        assert marker in text


@pytest.mark.parametrize(
    "markers",
    [
        (
            "behaviour scenarios first",
            "missing rows",
            "entry point",
            "failure or late result",
            "lifecycle",
            "concurrency",
            "platform",
            "unreachable rows",
            "wrong expected outcomes",
            "mocks that disagree with their real producer",
        ),
        (
            "concrete input",
            "wrong outcome",
            "violated requirement",
            "separate suggestion list",
            "`user-confirm`",
        ),
        ("fix to a finding", "state or asynchronous behaviour", "reviewed again"),
        ("Every scenario row has executed evidence or is reported open",),
    ],
    ids=["scenario-first", "findings", "re-review", "evidence"],
)
def test_should_review_behaviour_scenarios_and_distinguish_defects(
    markers: tuple[str, ...],
) -> None:
    text = _read_skill("mir-code", "code-review")
    step_two = next(line for line in text.splitlines() if line.startswith("2. "))
    assert "behaviour scenarios first" in step_two
    normalized = " ".join(text.split())
    for marker in markers:
        assert marker in normalized


@pytest.mark.parametrize("source", ["plugin", "manager"])
def test_should_emit_behaviour_scenario_hint_from_both_sessionstart_sources(
    source: str,
    tmp_path: Path,
) -> None:
    plugin = ROOT / "plugins/mir-lifecycle-hooks/hooks/runtime_continuity.py"
    manager = ast.parse((ROOT / "src/mir/core/capabilities/manager.py").read_text())
    embedded = next(
        ast.literal_eval(node.value)
        for node in manager.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_HOOK_HANDLER_SOURCE"
            for target in node.targets
        )
    )
    assert embedded == plugin.read_text()
    handler = plugin
    if source == "manager":
        handler = tmp_path / "runtime_continuity.py"
        handler.write_text(embedded)
    completed = subprocess.run(
        [sys.executable, str(handler)], capture_output=True, text=True, check=True
    )
    assert completed.stderr == ""
    assert "2 Design (+scenarios) -> 3 TDD" in completed.stdout


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


def test_portable_skills_do_not_require_mir_yoke_repository_state() -> None:
    bluebricks = _read_skill("mir-code", "bluebricks")
    governance = _read_skill("mir-core", "governance")
    memory_gc = _read_skill("mir-core", "memory-gc")
    knowledge = _read_skill("mir-content", "knowledge")
    automation = _read_skill("mir-core", "automation")
    verify = _read_skill("mir-core", "verify")

    assert "when present and relevant" in bluebricks
    assert "their absence is valid" in bluebricks
    assert "already owns `tasks/tdd.json`" in bluebricks
    assert "already repository-owned" in _read_skill("mir-code", "testing")
    assert "R20" not in governance
    assert "Phase 2" not in governance
    assert "mir memory gc" not in memory_gc
    normalized_knowledge = " ".join(knowledge.lower().split())
    assert "do not assume a shared service" in normalized_knowledge
    assert "agent-browser CLI" not in automation
    assert "21-element baseline" not in verify


def test_all_portable_skills_omit_provider_migration_milestones() -> None:
    forbidden = (
        "P15-I",
        "R20",
        "Phase 2",
        "21-element baseline",
        "mir memory gc",
        "agent-browser CLI",
    )

    for skill_path in sorted((ROOT / "plugins").glob("*/skills/*/SKILL.md")):
        text = skill_path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"{skill_path.relative_to(ROOT)}: {marker}"
