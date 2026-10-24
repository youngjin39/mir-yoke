"""Advisory defect corrections and bounded gap recipes for 0.13.30."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def read(target, name="SKILL.md"):
    plugin, skill = target.split("/")
    return (ROOT / "plugins" / plugin / "skills" / skill / name).read_text()


REFERENCES = (
    ("mir-core/design", "pre-spec-intent-audit.md", "fn-opt/dryforge at f5aa6d7",
     ("independent reviewer", "dialogue", "disposition", "omitted decisions", "owner",
      "before", "freeze", "bounded", "advisory")),
    ("mir-code/bluebricks", "bounded-task-integration.md", "fn-opt/dryforge at f5aa6d7",
     ("ownership", "dependencies", "shared writes", "regeneration", "barrier",
      "failed worktrees", "integrated result", "Main")),
    ("mir-core/design", "frontier-interview.md", "mattpocock/skills at 5beb35b",
     ("conversation-only", "no repository or workspace", "prototype", "throwaway",
      "authorized", "observed", "frontier")),
    ("mir-content/korean-writing", "long-form-finish.md",
     "bear2u/natural-korean-skills at 2a4f1fc (ideas only, no license; wording original)",
     ("\uac1c\uc694", "\ubb38\ub2e8\uc758 \uccab \ubb38\uc7a5", "\uc911\ubcf5",
      "\ube48 \uc81c\ubaa9", "\uc784\uc2dc \ubb38\uad6c", "\uc57d\uc5b4", "\uc6a9\uc5b4",
      "\uc694\uccad\ud55c \ud615\uc2dd", "\ubb38\uccb4 \ud504\ub85c\ud544",
      "\uc18c\uc720\uc790\uac00 \uc694\uccad", "\uc4f0\uae30 \uad8c\ud55c")),
    ("mir-core/design", "consequential-choice.md", "Q00/ouroboros at 825bc68",
     ("decision mode", "recommendation first", "grounds", "strongest dissent",
      "observable", "reverse", "stall", "advisory")),
    ("mir-core/spec-architect", "approved-spec-to-issues.md", "Q00/ouroboros at 825bc68",
     ("acceptance criteria", "parent", "child", "draft", "destination", "duplicates",
      "exact writes", "explicit authority", "Main")),
    ("mir-core/app-investigation", "bounded-investigation.md", "morluto/rea at cd10ee1 (MIT)",
     ("owner", "original", "candidate", "identities", "case kinds", "comparable evidence",
      "invalidate", "contradictions", "existing report or matrix", "9e6c624", "unlicensed")),
)


@pytest.mark.parametrize("target,reference,provenance,terms", REFERENCES)
def test_should_deliver_bounded_gap_recipe_with_pointer(target, reference, provenance, terms):
    text = read(target, "references/" + reference)
    assert f"Inspired by {provenance}." in text
    normalized = " ".join(text.lower().split())
    for term in terms:
        assert term.lower() in normalized, term
    assert len(text.splitlines()) < 50
    assert f"](references/{reference})" in read(target)


def test_should_require_execution_beyond_verification_declaration():
    text = read("mir-core/spec-architect", "references/04-artifacts.md")
    assert "verification declared" in text
    assert "executed results for the checked revision" in text
    assert "| Is this feature verified |" not in text


def test_should_encode_task_coverage_with_fixed_edge_endpoints():
    text = read("mir-core/spec-architect", "references/04-artifacts.md")
    assert "| `has_req` | FEAT/TASK → REQ |" in text
    assert "| `realized_by` | REQ/TASK → MOD |" in text
    assert "TASK → REQ" in text and "TASK → MOD" in text
    assert "graph's covers edges" not in text


def test_should_define_reproducible_per_axis_l1_denominator():
    text = read("mir-core/spec-architect", "references/00-completeness.md")
    assert "A=4, B=2, C=3, D=5, E=5, F=1, G=1, H=4; total=25" in text
    assert "sum of the eight per-axis subject counts" in text
    assert "8 axes x (entity count + actor count)" not in text
    assert "L1 48 cells" not in text


def test_should_preserve_technical_terms_despite_style_ban():
    text = read("mir-content/no-ai-slop")
    assert "meaningful technical terms and proper names" in text
    assert "a project or product name" in text and "test harness" in text
    assert "Banned outright:" not in text


def test_should_route_review_by_purpose():
    for target in ("mir-code/bluebricks", "mir-code/code-review", "mir-core/verify"):
        text = read(target)
        assert "diff and PR review → code-review" in text
        assert "completion evidence and spec compliance → verify" in text
        assert "architecture analysis → bluebricks" in text
    assert "PR review" not in read("mir-code/bluebricks").split("---")[1]
    assert "post-review code review" not in read("mir-core/verify")


def test_should_scope_gui_steps_to_changed_gui_behavior():
    text = read("mir-code/testing")
    assert "When the change affects GUI behavior and computer-use MCP is enabled:" in text
    assert "When the project has GUI components and computer-use MCP is enabled:" not in text


def test_should_use_qualitative_readiness_without_implied_dashboard():
    text = read("mir-core/efficiency")
    assert "qualitative" in text
    assert "100 points" not in text and "For AI-readiness, score" not in text
    assert "not a dashboard implementation" in text
    assert "instruction discoverability, modular boundaries, verification entry points" in text


def test_should_keep_current_and_historical_rea_provenance_distinct():
    text = read("mir-core/app-investigation")
    assert "Inspired by morluto/rea at cd10ee1 (MIT)." in text
    assert "9e6c624" in text and "unlicensed when first adapted" in text


def test_should_ground_identifiers_before_assertion_or_use():
    text = read("mir-code/bluebricks")
    assert "Before asserting or using unfamiliar or version-sensitive" in text
    assert "API names, flags, package names, versions or commit identifiers" in text
    assert "project code, installed interfaces or authoritative docs" in text
    assert "leave unknowns explicit" in text
    assert "Inspired by drona23/claude-token-efficient at 0d30a6d." in text


def test_should_separate_forward_readiness_from_executed_verification():
    artifacts = read("mir-core/spec-architect", "references/04-artifacts.md")
    gate = read("mir-core/spec-architect", "references/02-ai-ready-gate.md")
    skill = read("mir-core/spec-architect")
    assert "forward spec may be ready with a declared check method" in artifacts
    assert "once code exists (MODE-R or after implementation)" in artifacts
    assert "Missing code anchors or `verified_by` do not demote forward readiness" in artifacts
    assert "Implementability readiness is distinct from executed verification" in gate
    assert "Do not do it without the user's approval" in artifacts
    assert "report missing bindings without changing implementability readiness" in skill
    assert (
        "without an anchor is an unverified requirement and returns to ARR-8 incomplete"
    ) not in artifacts
    assert (
        "| Missing verification | `status: ready` with no `verified_by` | "
        "Return to ARR-8 incomplete |"
    ) not in artifacts


def test_should_apply_one_gateway_actor_boundary():
    skill = read("mir-core/spec-architect")
    method = read("mir-core/spec-architect", "references/01-methodology.md")
    equality = "External entity set = actor set minus {Timer, Gateway}"
    assert equality in skill and equality in method
    assert "Actor = the context model's external entities ∪ {Gateway, Timer}." in method
    assert "Actor = the context model's external entities ∪ {Timer}." not in method
    assert "External entity set = actor set (excluding Timer)" not in method


def test_should_allow_target_evidence_and_commands_in_designated_fields():
    text = read("mir-core/spec-architect")
    assert "private agent-host paths, session details or runtime-specific tool names" in text
    assert "except target-repository-relative evidence paths (MODE-R `file:line`)" in text
    assert "verification commands in their designated fields" in text
    assert "Do not put internal paths, tool names, or session identifiers in the output" not in text
    assert "Do not put tool- or platform-specific syntax or paths in the spec, except" in text


def test_should_route_as_built_analysis_and_unresolved_design_choices():
    precedence = (
        "Architecture precedence: existing, as-built architecture analysis → bluebricks; "
        "unresolved architecture choices and new design → design."
    )
    for target in ("mir-code/bluebricks", "mir-core/design"):
        assert precedence in read(target)
    assert "When a design or architecture needs audit or analysis." not in read("mir-core/design")


def test_should_keep_contextual_exceptions_in_writing_eval():
    text = read("mir-content/no-ai-slop", "references/eval.md")
    assert "meaningful technical terms and proper names" in text
    assert "adverbs and phrases that carry emphasis, uncertainty, contrast" in text
    assert "the writer's natural spoken rhythm" in text
    assert "removed unless quoted as examples?" not in text


def test_should_describe_no_ai_slop_local_adaptation():
    text = read("mir-content/no-ai-slop")
    assert "small local adaptation" in text
    assert "technical-term/proper-name exception" in text
    assert "behaviour\nis unchanged" not in text


def test_should_finish_long_form_in_korean_without_changing_provenance():
    text = read("mir-content/korean-writing", "references/long-form-finish.md")
    assert text.startswith(
        "# \ud55c\uad6d\uc5b4 \uc7a5\ubb38 \uae00 \ub9c8\ubb34\ub9ac\ud558\uae30\n"
    )
    assert (
        "Inspired by bear2u/natural-korean-skills at 2a4f1fc "
        "(ideas only, no license; wording original)."
    ) in text
    assert "\uc77d\uc9c0 \uc54a\uc740 \ubcf8\ubb38" in text
    assert "\uae30\uc874 \ud504\ub85c\uc81d\ud2b8 \ubb38\uc11c\ub098 \uba54\ubaa8\ub9ac" in text
    assert "\uc0c8 \uc800\uc7a5\uc18c" in text
    assert "Use this optional advisory pass" not in text


def test_should_choose_korean_diagnosis_before_revision_workflow():
    skill = read("mir-content/korean-writing")
    reference = read("mir-content/korean-writing", "references/contextual-revision.md")
    assert (
        '\uc9c4\ub2e8 \uc804\uc6a9\uacfc \uc218\uc815 \uc911 \uc694\uccad\uc5d0 '
        '\ub9de\ub294 \ubc29\uc2dd\uc744 \uba3c\uc800 \uc120\ud0dd\ud569\ub2c8'
        '\ub2e4'
    ) in skill
    assert skill.index(
        "\uc9c4\ub2e8 \uc804\uc6a9\uacfc \uc218\uc815"
    ) < skill.index(
        "\uc218\uc815 \ubc29\uc2dd\uc5d0\uc11c\ub294 \uc9c4\ub2e8, \uc218\uc815, \uc7ac\uac80\ud1a0"
    )
    for text in (skill, reference):
        assert "\uc6d0\ubb38\uc744 \ubcc0\uacbd\ud558\uc9c0 \uc54a\uace0" in text
        assert "\uc704\uce58\uc640 \uc6b0\uc120\uc21c\uc704" in text
    assert (
        '\uc9c4\ub2e8 \uc804\uc6a9\uc5d0\uc11c\ub294 \uc218\uc815\xb7\uc7ac\uac80'
        '\ud1a0 \ub2e8\uacc4\ub97c \uc0dd\ub7b5\ud569\ub2c8\ub2e4'
    ) in reference
    assert (
        '\uc218\uc815 \ubc29\uc2dd\uc758 \uacb0\uacfc\uc5d0\ub294 \uc218\uc815'
        '\ud55c \uae00'
    ) in reference
    assert (
        '\ucd08\uc548\uc774 \uc788\uc73c\uba74 \uc9c4\ub2e8, \uc218\uc815, \uc7ac'
        '\uac80\ud1a0 \uc21c\uc11c\ub85c \uc9c4\ud589\ud569\ub2c8\ub2e4'
    ) not in skill
    assert (
        '\n\uacb0\uacfc\uc5d0\ub294 \uc218\uc815\ud55c \uae00\uacfc \uac04\ub2e8'
        '\ud55c \uc804\ud6c4 \uae30\ub85d\uc744 \uc81c\uacf5\ud569\ub2c8\ub2e4'
    ) not in reference


def test_should_route_korean_linguistic_diagnosis_and_generic_pattern_detection():
    skill = read("mir-content/korean-writing")
    assert (
        '\ud55c\uad6d\uc5b4 \ud45c\ud604\uacfc \ubb38\ub9e5\uc758 \uc9c4\ub2e8'
        '\uc740 \uc774 \uc2a4\ud0ac\uc758 \uc9c4\ub2e8 \uc804\uc6a9 \ubc29\uc2dd'
    ) in skill
    assert (
        '\ud55c\uad6d\uc5b4 AI \uc0c1\ud22c \ud45c\ud604 \ud0d0\uc9c0\ub9cc'
        ' \uc694\uccad\ud574\ub3c4 \uc774 \uc9c4\ub2e8 \uc804\uc6a9 \ubc29\uc2dd'
    ) in skill
    assert (
        '`mir-content:no-ai-slop`\uc758 Detect\ub294 \uc601\uc5b4 \uae00\uc5d0\ub9cc'
    ) in skill
    assert (
        '\uc77c\ubc18\uc801\uc778 AI \uc0c1\ud22c \ud45c\ud604 \ud0d0\uc9c0\ub9cc'
        ' \uc694\uccad\ud558\uba74 `mir-content:no-ai-slop`\uc758 Detect'
    ) not in skill
    assert "\uc77c\ubc18\uc801\uc778 \uc0c1\ud22c\uc801 \ud45c\ud604 \ud3b8\uc9d1\uc740" in skill
    assert (
        '\uc9c4\ub2e8, \uc218\uc815, \uc7ac\uac80\ud1a0 \uc21c\uc11c\ub85c \uc9c4'
        '\ud589\ud569\ub2c8\ub2e4'
    ) not in skill


def test_should_close_business_execution_fields_or_mark_undecided():
    text = read("mir-content/korean-writing", "references/business.md")
    assert (
        '\ubcf4\uace0\uc11c\ub098 \uc81c\uc548\uc11c\uc5d0\uc11c \uc2e4\ud589'
        '\uc744 \uc694\uccad\ud558\uba74'
    ) in text
    assert "\uc2e4\ud589 \ub2f4\ub2f9\uc790, \ub0a9\uae30\uc640 \ub2e4\uc74c \ud589\ub3d9" in text
    assert (
        '\uc815\ud558\uc9c0 \ubabb\ud55c \ud56d\ubaa9\uc740 \uac01\uac01 \u2018'
        '\ubbf8\uc815\u2019'
    ) in text
    assert (
        '\ubbf8\ud655\uc815 \uc0ac\uc2e4\uacfc \ud544\uc694\ud55c \ud655\uc778 '
        '\uc0ac\ud56d'
    ) in text
    assert len(text.splitlines()) < 50


def test_should_separate_migration_implementation_from_owner_intent():
    skill = read("mir-core/design")
    assert "](references/migration-policy-confirmation.md)" in skill
    text = read("mir-core/design", "references/migration-policy-confirmation.md")
    assert "Inspired by fn-opt/dryforge at f5aa6d7." in text
    for term in ("`code_confirmed`", "`user_confirmed`", "`derived`", "`not_applicable`",
                 "`unresolved`", "`conflict`", "implementation", "owner intent",
                 "dangerous inferred business or security policy", "existing owner evidence",
                 "targeted confirmation", "important intended rules absent from code",
                 "no mandatory layout or engine"):
        assert term in " ".join(text.split())
    assert "code confirmation alone never confirms owner intent" in text
    assert len(text.splitlines()) < 50


def test_should_traverse_file_module_requirement_feature_with_typed_edges():
    text = read("mir-core/spec-architect", "references/04-artifacts.md")
    assert "Choose traversal edges by input type" in text
    assert "path \u2192 `implemented_in\u207b\xb9` \u2192 MOD" in text
    assert (
        'MOD \u2192 `realized_by\u207b\xb9` \u2192 REQ \u2192 `has_req\u207b\xb9`'
        ' \u2192 FEAT'
    ) in text
    assert "file's `@spec` anchor to MOD or `implemented_in\u207b\xb9` \u2192 MOD" in text
    assert "| `implemented_in` | MOD \u2192 path |" in text
    assert "| `realized_by` | REQ/TASK \u2192 MOD |" in text
    assert "file's `@spec` anchor \u2192 `implemented_in\u207b\xb9` \u2192 REQ" not in text
    assert (
        'Reverse BFS from X over `realized_by\u207b\xb9`, `has_req\u207b\xb9`, `d'
        'epends_on\u207b\xb9`'
    ) not in text


@pytest.mark.parametrize("target,name", [
    ("mir-core/repo-maintenance", "SKILL.md"),
    ("mir-lifecycle-hooks/runtime-continuity", "references/default-work-method.md"),
])
def test_should_condition_cursor_writes_on_request_authority(target, name):
    text = read(target, name)
    assert "only when the request authorizes writes" in text
    assert "Read-only reviews record nothing and add no approval detour" in text
    assert "Record the request in the repository's active cursor, then" not in text
    assert "Record the user's intent in the repository's single active cursor and" not in text


def test_should_fall_back_when_optional_lifecycle_package_is_absent():
    text = read("mir-core/design")
    assert "When installed, follow the method order" in text
    assert "If `mir-lifecycle-hooks` is not installed" in text
    assert "repository's own documented method, or else the order in this skill" in text
    assert "\nFollow the method order in the `mir-lifecycle-hooks:runtime-continuity`" not in text


def test_should_mark_deliberate_limitations_during_implementation():
    text = read("mir-code/bluebricks")
    assert "implementation deliberately introduces a known limitation" in text
    assert "leave a `shortcut:` marker immediately" in text
    assert "ceiling and an observable upgrade trigger" in text
    pointer = "../code-review/references/repository-audit-and-debt.md"
    assert f"]({pointer})" in text
    assert (ROOT / "plugins/mir-code/skills/bluebricks" / pointer).is_file()


def test_should_verify_changing_external_facts_before_confirming_korean_drafts():
    text = read("mir-content/korean-writing")
    terms = (
        "\uc790\uaca9 \uc694\uac74", "\ub9c8\uac10\uc77c", "\uac00\uaca9", "\ubc95\uaddc",
        "\uacf5\uc2dd \ucd5c\uc2e0 \uc790\ub8cc", "\uc81c\uacf5\ud55c \ucd5c\uc2e0 \uc790\ub8cc",
        "\ud655\uc778\ud55c \ub4a4\uc5d0\ub9cc \ud655\uc815 \uc0ac\uc2e4",
        "\ucd9c\ucc98\uc758 \ub0a0\uc9dc\ub098 \ubc84\uc804",
        "\ubbf8\ud655\uc778 \ud56d\ubaa9", "\u2018\ucd08\uc548\u2019",
        "\u2018\ud655\uc778 \ud544\uc694\u2019",
    )
    for term in terms:
        assert term in text, term
    assert text.index(terms[0]) < text.index("\uba54\ubaa8\uc5d0\uc11c \uc2dc\uc791\ud558\uba74")


@pytest.mark.parametrize("name", [
    "SKILL.md", "references/00-completeness.md", "references/02-ai-ready-gate.md",
])
def test_should_keep_spec_readiness_advisory_to_main_and_owner(name):
    text = " ".join(read("mir-core/spec-architect", name).split())
    assert "Readiness and completeness judgments are advisory to Main and the owner." in text
    assert (
        "Only deterministic required checks and explicit owner decisions block implementation."
    ) in text
    assert "implementation cannot start" not in text
    if name == "references/00-completeness.md":
        assert "blueprint is incomplete for implementation; report it to Main" in text


def test_should_end_only_spec_repair_after_three_failures_and_keep_gaps():
    for name in ("SKILL.md", "references/02-ai-ready-gate.md"):
        text = " ".join(read("mir-core/spec-architect", name).split())
        assert "After three consecutive" in text
        assert "stop the spec-repair loop and return the additional information needed" in text
        assert "does not veto implementation the owner has already authorized" in text
        assert "gaps.yaml" in text
        assert (
            "Never report a gate failure as PASS" in text or "Never conceal a gate failure" in text
        )
        assert "failures, stop and return" not in text
    skill = read("mir-core/spec-architect")
    assert "| Gate failure | Expose every `GAP-nn`." in skill
    assert "After three consecutive failures, stop the spec-repair loop" in skill


def test_should_scope_automation_ledger_to_authorized_persistent_runs():
    text = read("mir-core/automation")
    assert "Ledger creation and updates apply only to persistent or long-running runs" in text
    assert "where write authority exists" in text
    assert "A one-off, read-only browser observation creates no record" in text
    assert "use step 4 and verify the requested outcome without a ledger" in text
    assert text.index("Ledger creation and updates") < text.index("1. Give the run")
    assert (
        "4. For browser work, use an available browser tool, take the best supported semantic "
        "snapshot,\n"
        "   perform the smallest action, and verify the resulting page state before the next "
        "action. If no\n"
        "   compatible browser capability exists, report the unevaluated browser boundary "
        "instead of\n"
        "   inventing a command."
    ) in text
    assert "## Workflow\n1. Give the run" not in text


def test_should_point_mode_s_to_the_existing_comparison_heading():
    skill = read("mir-core/spec-architect")
    heading = "MODE-S in detail (comparison)"
    assert f"03 \u00a7{heading}" in skill
    assert f"## {heading}" in read("mir-core/spec-architect", "references/03-reverse-recovery.md")
    assert "03 \u00a7Four-quadrant comparison" not in skill


def test_should_enumerate_change_reach_before_editing():
    text = " ".join(read("mir-code/bluebricks").split())
    assert "Before editing, enumerate callers, tests, fixtures, configs, exports" in text
    assert "cross-cutting sites" in text
    assert "adding to or removing from a collection" in text
    assert "tests or snapshots that hard-code its size or member set" in text
    assert "fix the root cause once in shared code" in text
    assert "Finish every reached site before reporting" in text
    assert "Tiny local edits need only a quick search" in text
    assert text.index("Before editing, enumerate") < text.index("3. Answer WHAT")
    for source in ("DietrichGebert/ponytail at 09c434a", "fn-opt/dryforge at f5aa6d7"):
        assert f"Inspired by {source}." in text


def test_should_define_the_installed_terse_output_baseline():
    text = " ".join(read("mir-core/efficiency").split())
    for term in (
        "Terse-output baseline:", "no sycophantic openers or closers",
        "do not restate the request", "lead with the result or answer",
        "no unsolicited suggestions beyond the task",
        "Expand when ambiguity, safety, verification or operational risk needs it",
        "Preserve exact commands, paths and identifiers",
        "Inspired by drona23/claude-token-efficient at 0d30a6d.",
    ):
        assert term in text, term


def test_should_default_manual_lesson_and_memory_notes_to_no_write():
    text = " ".join(read("mir-content/knowledge").split())
    for term in (
        "learned lesson or memory note", "default to no write",
        "positive note requires evidence that directly supports the claim "
        "or contradicts its premise",
        "Near-matches and insufficient evidence are never positive evidence",
        "omit them or retain them only as an explicitly labeled caution",
        "manual and write-authorized", "no learning loop",
        "Inspired by xiaowu0162/LongMemEval-V2 at 2cc8c54.",
        "Ideas only; wording is original",
    ):
        assert term in text, term
    assert text.index("default to no write") < text.index("4. Normalize")


def test_should_prefer_local_test_naming_over_the_fallback():
    text = " ".join(read("mir-code/testing").split())
    assert "Follow the repository's established test-naming convention" in text
    assert "only when none exists, use `should_return_X_when_Y`" in text
    assert "- Test names: `should_return_X_when_Y`." not in text
    assert "6. Follow local test patterns" in text


@pytest.mark.parametrize("target,present,absent", [
    ("mir-core/verify", (
        "verification — Evidence-gated completion",
        "multi-axis verification, optionally delegated when the host provides sub-agents",
    ), ("7-stage gate", "via multi-axis sub-agents")),
    ("mir-core/design", (
        "role-separated stages: design → independent review → delegated execution",
        "→ independent evaluation", "using whatever agents the host provides",
    ), ("Claude design → Codex review", "executor dev → Codex eval")),
])
def test_should_describe_legacy_intent_without_promising_runtimes(target, present, absent):
    text = " ".join(read(target).split())
    for term in present:
        assert term in text, term
    for term in absent:
        assert term not in text, term


def test_should_report_coverage_only_from_a_coverage_tool():
    text = " ".join(read("mir-code/testing").split())
    assert "Fill Coverage only from a coverage tool's output" in text
    assert 'otherwise write "not measured"' in text
    assert "{% or not measured}" in text
    assert "| {file} | {N} | {N} | {N} | {%} |" not in text


def test_should_route_korean_drafts_from_the_local_adaptation_area():
    text = read("mir-content/no-ai-slop")
    adaptation = text.split("\n## Provenance\n", 1)[1]
    assert (
        "Korean-language drafts, diagnosis and revision route to `mir-content:korean-writing`; "
        "no-ai-slop's word and pattern lists are English."
    ) in adaptation


def test_should_include_grill_requests_in_design_triggers():
    frontmatter = read("mir-core/design").split("---")[1]
    assert "grill me, stress-test a plan" in frontmatter
    assert "role-split, interview, grill me, stress-test a plan" in frontmatter
    description = frontmatter.split('description: "', 1)[1].rsplit('"', 1)[0]
    assert len(description) <= 1024


def test_should_split_spec_audit_from_repository_audit_triggers():
    verify = read("mir-core/verify").split("---")[1]
    review = read("mir-code/code-review").split("---")[1]
    verify_triggers = verify.split("Trigger: ", 1)[1].split(r"\n", 1)[0].split(", ")
    assert "self-audit" in verify_triggers and "spec audit" in verify_triggers
    assert "audit" not in verify_triggers
    assert (
        "Trigger: code review, pull request review, quality check, merge check, repository audit."
    ) in review
    for target in ("mir-core/verify", "mir-code/code-review"):
        assert "completion evidence and spec compliance → verify" in read(target)


def test_should_reuse_the_repository_cursor_before_creating_a_run_ledger():
    text = " ".join(read("mir-core/automation").split())
    assert "use the repository's existing cursor or task ledger when one exists" in text
    assert "Never create a second cursor" in text
    assert (
        "Create a run ledger only when the repository has none and write authority exists"
    ) in text
    assert "record its goal, owner, current checkpoint, and completion test there" in text
    assert "completion test in a repository-owned task ledger" not in text


def test_should_preserve_genre_register_and_voice_with_default_prose_exception():
    text = " ".join(read("mir-content/korean-writing").split())
    for term in (
        "\uc0b0\ucd9c\ubb3c", "\uc7a5\ub974",
        "\ubcf4\uc874\ud560 \uc791\uc131\uc790\uc758 \ub9d0\ud22c",
        "\ud574\ub77c\uccb4 \uc5d0\uc138\uc774",
        "\uac1c\uc870\uc2dd \ubc1c\ud45c \uc790\ub8cc\uc640 \ubaa9\ub85d",
        "\uc874\ub313\ub9d0\uacfc \ubb38\uc7a5 \uc885\uacb0 \uaddc\uce59\ubcf4\ub2e4 \uc6b0\uc120",
        "\uc5d0\uc774\uc804\ud2b8\uc758 \uc548\ub0b4 \uba54\uc2dc\uc9c0\uc640 "
        "\uae30\ubcf8 \uc0b0\ubb38",
        "`mir-content:fluent-korean`\uc744 \ub530\ub985\ub2c8\ub2e4",
    ):
        assert term in text, term
    assert (
        "\ub450 \uc2a4\ud0ac\uc758 \uaddc\uce59\uc744 \ub2e4\uc2dc "
        "\ub098\uc5f4\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4"
    ) in text


def test_should_batch_tbd_questions_by_settled_prerequisite_frontier():
    text = " ".join(read("mir-core/spec-architect", "references/00-completeness.md").split())
    assert "present the `tbd` cells together by frontier" in text
    assert "as in the design skill's frontier interview" in text
    assert "depends on another open cell waits for a later round" in text
    assert "Do not ask cell by cell" in text
    assert "then present the `tbd` cells together. Do not ask" not in text


def test_should_observe_safe_permitted_runnable_deliverables_beside_unit_tests():
    text = " ".join(read("mir-core/verify").split())
    start = text.index("2. Map each claim")
    end = text.index("3. Run checks", start)
    step = text[start:end]
    for term in (
        "runnable service, CLI or UI", "beside the unit tests",
        "runs it and observes a real response or effect", "safe and permitted",
        "otherwise label that claim unevaluated",
    ):
        assert term in step, term
    assert "runtime probe, or direct artifact inspection. 3. Run" not in text
    assert text.count("Inspired by fn-opt/dryforge at f5aa6d7.") == 1


def test_should_offer_report_only_reframing_for_user_reported_stalls():
    skill = read("mir-core/automation")
    reference = read("mir-core/automation", "references/recovery-and-reframing.md")
    assert "For Main-directed or user-reported stall diagnosis" in skill
    assert "For Main-directed stall diagnosis" not in skill
    text = " ".join(reference.split())
    assert "report-only advice for Main-directed or user-reported stalls" in text
    assert "report-only advice for Main after a stall or repeated failure" not in text
    assert "Main chooses any next action" in text
    assert "none is automatically authorized here" in text
    assert len(reference.splitlines()) < 50


@pytest.mark.parametrize("target,existing,added", [
    ("mir-core/automation",
     "runner, long-running, background, monitor, resume, compact, handoff, browser, scrape, E2E",
     "stuck, going in circles, tried everything"),
    ("mir-core/governance",
     "instruction docs, governance review, project doctor, registry optimization, "
     "or multi-repository policy analysis",
     "improve a skill from past sessions, skill patch from traces"),
    ("mir-core/efficiency",
     "token efficiency, session efficiency, Claude usage report, Codex usage report, "
     "cost analysis, AI readiness, repo cartography",
     "concise output, terse responses"),
])
def test_should_discover_existing_advice_without_losing_triggers(target, existing, added):
    frontmatter = read(target).split("---")[1]
    description = json.loads(frontmatter.split("description: ", 1)[1].strip())
    assert existing in description
    assert added in description
    assert len(description) <= 1024


def test_should_close_assumed_load_bearing_decisions_before_freeze():
    text = " ".join(read("mir-core/design").split())
    intent = text.split("## Intent Extraction", 1)[1].split("## Status", 1)[0]
    for term in (
        "Before a design or spec is frozen, no load-bearing decision remains `assumed`",
        "Resolve from available evidence first", "ask the owner about open domain and policy",
        "present technical decisions with a recommendation", "mark tuning values `tunable`",
        "Surface only genuinely open, high-cost decisions",
        "do not turn settled decisions into extra questions",
    ):
        assert term in intent, term
    assert "Inspired by fn-opt/dryforge at f5aa6d7." in text
    assert "load-bearing decisions may remain `assumed`" not in intent


def test_should_judge_three_korean_cues_as_fix_or_keep_in_context():
    text = read("mir-content/korean-writing", "references/contextual-revision.md")
    cues = (
        (
            '\ub0b4\uc6a9 \uc5c6\uc774 \ubd99\uc778 \uc0c1\ud22c \ubb38\uad6c',
            '\uc0c8 \uc815\ubcf4 \uc5c6\uc774 \ubd84\ub7c9\ub9cc \ub298\ub9ac\uba74 \ub35c'
            '\uc5b4 \ub0b4\uace0',
            '\uc758\ub840\ub098 \uc7a5\ub974\uc0c1 \ud544\uc694\ud55c \ud45c\ud604\uc774'
            '\uba74 \ubcf4\uc874',
        ),
        (
            '\ud589\ub3d9\uc744 \ubb49\ub6b1\uadf8\ub9b0 \ub3d9\uc0ac',
            '\uc2e4\uc81c \ud589\ub3d9\uc744 \uc54c \uc218 \uc5c6\uc73c\uba74 \uad6c\uccb4'
            '\uc801\uc73c\ub85c \ubc14\uafb8\uace0',
            '\uc774\ubbf8 \ub300\uc0c1\uacfc \ud589\ub3d9\uc774 \ubd84\uba85\ud558\uba74 '
            '\uc720\uc9c0',
        ),
        (
            '\ubb38\ub2e8 \uccab\uba38\ub9ac\uc758 \uc811\uc18d\uc5b4 \ubc18\ubcf5',
            '\ubb38\ub2e8 \uad00\uacc4\ub97c \ub4dc\ub7ec\ub0b4\ub294\uc9c0 \uc0b4\ud3b4',
            '\ubd88\ud544\uc694\ud558\uba74 \ub35c\uc5b4 \ub0b4\uace0 \ud544\uc694\ud55c '
            '\uc5f0\uacb0\uc740 \uc720\uc9c0',
        ),
    )
    for cue, fix, keep in cues:
        row = next((line for line in text.splitlines() if line.startswith(f"| {cue} |")), "")
        assert fix in row and keep in row, cue
    assert "\ub2e8\uc11c\uac00 \uc788\ub2e4\ub294 \uc774\uc720\ub9cc\uc73c\ub85c" in text
    assert "\uc624\ub958\ub85c \ud310\uc815\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4" in text
    assert "\ubaa8\ub4e0 \uc0c1\ud22c \ubb38\uad6c\ub97c \uc0ad\uc81c\ud569\ub2c8\ub2e4" not in text
    assert len(text.splitlines()) < 50


def test_should_answer_memory_questions_from_exact_premise_aware_records():
    text = " ".join(read("mir-content/knowledge").split())
    for term in (
        "When answering from repository memory or notes", "cite the exact supporting record",
        "evidence contradicts the question's premise, state the contradiction",
        "never substitute a near-match record",
        "keep conflicting records as an explicit unknown",
    ):
        assert term in text, term
    assert "use a near-match record as support" not in text
    assert "Inspired by xiaowu0162/LongMemEval-V2 at 2cc8c54." in text
    assert "Ideas only; wording is original" in text


@pytest.mark.parametrize("name", ["SKILL.md", "references/contextual-revision.md"])
def test_should_apply_only_general_no_ai_slop_principles_to_korean(name):
    text = read("mir-content/korean-writing", name)
    for term in (
        (
            '\ud55c\uad6d\uc5b4\uc5d0\ub294 \ube48 \uc694\uc57d \uacb0\ub9d0\uc744 '
            '\ub35c\uace0 \uad6c\uccb4\uc801\uc778 \uc8fc\uc7a5\uc744 \uc4f0\uba70'
        ),
        (
            '\uae00\uc4f4\uc774\uc758 \ub9d0\ud22c\ub97c \uc9c0\ud0a4\ub294 \uc77c'
            '\ubc18 \uc6d0\uce59\ub9cc \uc801\uc6a9\ud558\uace0'
        ),
        (
            '\uc601\uc5b4 \ub2e8\uc5b4\xb7\ud328\ud134 \ubaa9\ub85d\uc740 \uc801'
            '\uc6a9\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4'
        ),
    ):
        assert term in text, term
    assert (
        '\ud55c\uad6d\uc5b4\uc5d0\ub3c4 \uc601\uc5b4 \ub2e8\uc5b4\xb7\ud328'
        '\ud134 \ubaa9\ub85d\uc744 \uc801\uc6a9'
    ) not in text
    if name == "SKILL.md":
        assert (
            '`mir-content:no-ai-slop`\uc744 \ucc38\uace0\ud569\ub2c8\ub2e4. \ub450 '
            '\uc2a4\ud0ac'
        ) not in text
    else:
        assert (
            '`mir-content:no-ai-slop`\uc744 \ucc38\uace0\ud569\ub2c8\ub2e4. \uc5ec'
            '\uae30\uc11c\ub294'
        ) not in text


def test_should_expose_per_turn_inventory_and_placement_at_efficiency_pointer():
    text = read("mir-core/efficiency")
    pointer = next(line for line in text.splitlines()
                   if "](references/instruction-change-evaluation.md)" in line)
    for term in ("per-turn input inventory", "always, conditional or historical placement",
                 "instruction-change comparisons"):
        assert term in pointer, term
    assert "[the optional reference](references/instruction-change-evaluation.md)" not in text
    frontmatter = text.split("---")[1]
    description = json.loads(frontmatter.split("description: ", 1)[1].strip())
    assert "per-turn token load" in description
    assert len(description) <= 1024


def test_should_describe_existing_pretooluse_handoff_guard_without_changing_sessionstart():
    text = " ".join(read("mir-lifecycle-hooks/runtime-continuity").split())
    assert "UserPromptSubmit/PreToolUse/Stop hooks" in text
    assert (
        "PreToolUse guards commands and file writes "
        "during narrowly detected handoff turns"
    ) in text
    assert "SessionStart stays unchanged" in text
    assert "UserPromptSubmit/Stop hooks" not in text
    hooks = json.loads((ROOT / "plugins/mir-lifecycle-hooks/hooks/hooks.json").read_text())["hooks"]
    for event in ("UserPromptSubmit", "PreToolUse", "Stop"):
        handler = hooks[event][0]["hooks"][0]
        assert "skills/runtime-continuity/scripts/handoff_packet.py" in handler["command"]
        assert handler["timeout"] == 8


@pytest.mark.parametrize("target", ["mir-code/code-review", "mir-core/repo-maintenance"])
def test_should_share_whole_repository_audit_precedence(target):
    line = (
        "Audit precedence: code-quality, debt and risk audit of code \u2192 code-review; "
        "periodic multi-item repository checkup \u2192 repo-maintenance; "
        "instruction-document and registry governance \u2192 governance; "
        "AI-readiness review \u2192 efficiency."
    )
    text = read(target)
    assert line in text.splitlines()
    assert "all whole-repository audits \u2192 repo-maintenance" not in text


def test_should_write_back_verified_change_intent_only_to_affected_existing_docs():
    text = " ".join(read("mir-code/bluebricks").split())
    step = text.split("9. Record a newly discovered hazard", 1)[1].split(
        "## Bluebrick Checklist", 1,
    )[0]
    for term in (
        "After verifying a feature or fix, and only with write authority",
        "re-read the governing intent (spec, plan, handoff or cursor)",
        "existing durable docs affected by the change",
        "architecture, business rules, security and engineering notes",
        "intended behavior, not only code behavior",
        "both directions: changed behavior against docs and doc statements against the change",
        "Escalate conflicting in-scope content instead of overwriting it",
        "Create no new doc tree or layout; skip this for tiny local edits",
    ):
        assert term in step, term
    assert "update all repository docs after every edit" not in text


@pytest.mark.parametrize("reference,terms", [
    ("technical-runbooks.md", (
        '\uc124\uce58 \uc548\ub0b4',
        'API/SDK \uc548\ub0b4',
        'ADR',
        (
            '\uacb0\uc815\uc744 \ub2e4\uc2dc \uac80\ud1a0\ud560'
            ' \uc870\uac74'
        ),
        '\ubb38\uc81c \ud574\uacb0 \uc548\ub0b4',
        (
            '\uad00\ucc30\ud55c \uc99d\uc0c1\uacfc \uc6d0\uc778'
            ' \uac00\uc124\uc744 \uad6c\ubd84'
        ),
        '\ub9c8\uc774\uadf8\ub808\uc774\uc158',
        (
            '\uc0ac\uc804 \uc870\uac74, \uad8c\ud55c,'
            ' \uc21c\uc11c, \uc608\uc0c1 \uacb0\uacfc'
            ', \ud655\uc778 \ubc29\ubc95\uacfc \uc2e4'
            '\ud328 \uc2dc \ubcf5\uad6c \uacbd\ub85c'
        ),
    )),
    ("public-notices.md", (
        '\uac8c\uc2dc \uc804 \ud655\uc778',
        '\uac1c\uc778\uc815\ubcf4',
        (
            '\ud544\uc694\ud55c \uc2b9\uc778\uacfc \ubc95\ub960'
            ' \uac80\ud1a0'
        ),
        (
            '\ubc18\ub4dc\uc2dc \ud574\uc57c \ud558\ub294 '
            '\ud589\ub3d9\uacfc \uc120\ud0dd\ud560 \uc218 '
            '\uc788\ub294 \ud589\ub3d9\uc744 \uad6c\ubcc4'
        ),
    )),
])
def test_should_cover_korean_technical_forms_and_notice_publication(reference, terms):
    text = read("mir-content/korean-writing", "references/" + reference)
    for term in terms:
        assert term in text, term
    assert len(text.splitlines()) < 50
    assert (
        '\ubaa8\ub4e0 \uae30\uc220 \ubb38\uc11c\ub294 '
        '\uc6b4\uc601 \uc808\ucc28\uc640 \uac19\uc740 '
        '\uc21c\uc11c\ub85c \uc501\ub2c8\ub2e4'
    ) not in text
    assert (
        '\uc120\ud0dd \uc0ac\ud56d\ub3c4 \uc758\ubb34\ub85c'
        ' \ud45c\uc2dc\ud569\ub2c8\ub2e4'
    ) not in text


def test_should_stage_instruction_doc_proposals_under_the_same_trace_rules():
    text = " ".join(read("mir-core/governance", "references/skill-patch-from-traces.md").split())
    for term in (
        "owner-invoked skill or instruction-document maintenance",
        "CLAUDE.md, AGENTS.md and their canonical sources",
        "same edit budget, held-out comparison, staging and owner adoption rules",
        "Generated derivatives are regenerated, never hand-edited",
        "Main chooses an explicit subset, including none",
    ):
        assert term in text, term
    assert "Use only for owner-invoked skill maintenance" not in text
    reference = read("mir-core/governance", "references/skill-patch-from-traces.md")
    assert len(reference.splitlines()) < 50
    description = read("mir-core/governance").splitlines()[2]
    assert "improve instruction docs from past sessions" in description


def test_should_route_korean_ai_diagnosis_from_both_descriptions():
    description = read("mir-content/korean-writing").splitlines()[2]
    for trigger in ("AI \ud2f0", "AI \uc0c1\ud22c \ud45c\ud604", "\ud55c\uad6d\uc5b4 \uc9c4\ub2e8"):
        assert trigger in description
    english = read("mir-content/no-ai-slop").splitlines()[2]
    assert "Korean-language text routes to `mir-content:korean-writing`." in english
    assert english.endswith("Korean-language text routes to `mir-content:korean-writing`.")
    assert not english.endswith("or asks whether writing reads as AI.")


def test_should_ask_every_unresolved_human_decision_in_explicit_grills():
    text = " ".join(read("mir-core/design").split())
    for term in (
        "For an owner-invoked grill or frontier interview",
        "override the high-cost filter and tuning defaults",
        "ask every unresolved human decision", "derive facts first",
        "leave nothing load-bearing silently assumed",
    ):
        assert term in text, term
    reference = read("mir-core/design", "references/frontier-interview.md")
    assert "filtering of answered, derivable or tunable decisions" not in reference
    assert "answered or derivable decisions" in reference
    assert "Outside owner-invoked interviews, retain tuning defaults" in reference


def test_should_discover_controlled_experiments_without_losing_test_triggers():
    description = json.loads(read("mir-code/testing").splitlines()[2].split(": ", 1)[1])
    assert (
        "test, TDD, unit test, integration test, experiment, benchmark, performance comparison"
    ) in description
    assert not description.endswith("integration test")
    assert len(description) <= 1024



def test_should_discover_ordinary_memory_and_notes_lookups():
    text = read("mir-content/knowledge")
    description = json.loads(text.splitlines()[2].split(": ", 1)[1])
    for trigger in (
        "knowledge, wiki, ingest, knowledge graph, taxonomy, provenance, contradiction",
        "stale-claim, orphan, or knowledge-lint work",
        "answer from notes or memory", "what did we decide", "prior decision lookup",
    ):
        assert trigger in description, trigger
    assert not description.endswith("or knowledge-lint work.")
    assert "cite the exact supporting record" in text
    assert "a near-match record" in text
    assert len(description) <= 1024


def test_should_confirm_each_scope_bearing_free_text_answer_before_frontier_update():
    reference = read("mir-core/design", "references/frontier-interview.md")
    step = " ".join(reference.split("4. ", 1)[1].split("5. ", 1)[0].split())
    for term in (
        "free-text answer carrying scope, constraints or exclusions",
        "restate it in one line", "confirm it with the user",
        "next round's numbered list", "Before recording a decision or recomputing",
        "Keep dependent questions deferred until confirmation",
    ):
        assert term in step, term
    assert "Wait for answers, then recompute the tree and frontier" not in reference
    assert len(reference.splitlines()) < 50


def test_should_prove_unused_code_before_deletion_and_consider_merge_or_split():
    reference = read("mir-code/code-review", "references/repository-audit-and-debt.md")
    text = " ".join(reference.split())
    for term in (
        "Before recommending deletion of apparently unused code",
        "search the whole tree", "tests, config, fixtures",
        "dynamic or string references", "otherwise label the finding unproven",
        "merge or split", "Inspired by DietrichGebert/ponytail at 09c434a.",
    ):
        assert term in text, term
    assert "reuse existing code or built-ins before new machinery" not in text
    assert len(reference.splitlines()) < 50


@pytest.mark.parametrize("target", ["mir-core/automation", "mir-core/ontology"])
def test_should_share_handoff_resume_and_run_state_precedence(target):
    line = (
        "Routing precedence: writing or receiving a brief or handoff for another agent "
        "→ ontology Handoff packet; resuming after a session transition or compaction "
        "→ mir-lifecycle-hooks:runtime-continuity; persistent or long-running run state "
        "→ automation."
    )
    text = read(target)
    assert line in text.splitlines()
    assert "all handoff and resume requests → automation" not in text
    assert "all handoff and resume requests → ontology" not in text
