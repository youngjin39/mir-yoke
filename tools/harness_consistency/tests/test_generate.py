from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from tools.harness_consistency.cli import build_parser
from tools.harness_consistency.generate import build_manifest
from tools.harness_consistency.runner import run, run_with_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _schema() -> dict:
    return json.loads(
        (PROJECT_ROOT / "config" / "harness-consistency.schema.json").read_text(
            encoding="utf-8",
        )
    )


def _role_policy_render_args(manifest: dict) -> list[str]:
    surfaces = manifest["rule_inputs"]["generated_marker_rerender"]["surfaces"]
    return next(
        surface["render_args"]
        for surface in surfaces
        if surface["file"] == "CLAUDE.md"
        and surface["render_module"] == "tools.profile_compiler"
    )


def test_build_manifest_real_repo_section_and_rules() -> None:
    manifest = build_manifest(
        PROJECT_ROOT,
        PROJECT_ROOT / "config" / "repos" / "mir-yoke.json",
    )

    assert manifest["repo"] == {
        "slug": "mir-yoke",
        "repository_type": "template_transitional",
        "role": "code_tdd_review_plane",
        "fleet_manager": True,
        "enforcement": {
            "tools_commit_gate": "deferred",
            "tools_tdd_ledger": "keyed_composite",
        },
    }
    assert len(manifest["rules"]) == 17
    # template source manifest has R3+R8 disabled
    assert manifest["_generated"]["repo_slug"] == "mir-yoke"
    assert "repo_root" not in manifest["_generated"]
    assert "/" not in manifest["_generated"]["repo_slug"]
    assert "disabled_rules" not in manifest["_generated"]


def test_build_manifest_schema_validates_real_repo() -> None:
    manifest = build_manifest(
        PROJECT_ROOT,
        PROJECT_ROOT / "config" / "repos" / "mir-yoke.json",
    )

    jsonschema.validate(instance=manifest, schema=_schema())


def test_build_manifest_introspects_hooks(tmp_path: Path) -> None:
    archive_dir = tmp_path / ".claude" / "hooks" / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "foo-hook.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    live_hook = tmp_path / ".claude" / "hooks" / "live-hook.sh"
    live_hook.write_text(
        "#!/bin/sh\n_MIR_HOOK_TIER=\"warn\"\n",
        encoding="utf-8",
    )

    manifest = build_manifest(tmp_path, None)

    rule_inputs = manifest["rule_inputs"]
    assert (
        "foo-hook"
        in rule_inputs["archived_source_phase_doc"]["archived_hook_names"]
    )
    assert rule_inputs["hook_tier_declaration"]["expected_tiers"] == {
        "live-hook.sh": "warn"
    }


def test_build_manifest_non_fleet_manager_defaults(tmp_path: Path) -> None:
    profile_path = tmp_path / "config" / "repos" / "app.json"
    _write_json(
        profile_path,
        {
            "slug": "app",
            "repository_type": "code_app",
        },
    )

    manifest = build_manifest(tmp_path, profile_path)

    assert manifest["repo"]["role"] == "code_tdd_review_plane"
    assert manifest["repo"]["fleet_manager"] is False
    assert manifest["repo"]["enforcement"] == {
        "tools_commit_gate": "lint_test",
        "tools_tdd_ledger": "changes_array",
    }


def test_build_manifest_localizes_generated_metadata_and_role_policy_surface(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "demo-fam.json"
    _write_json(
        profile_path,
        {
            "slug": "demo-fam",
            "repository_type": "code_app",
        },
    )

    manifest = build_manifest(PROJECT_ROOT, profile_path)
    render_args = _role_policy_render_args(manifest)

    assert manifest["_generated"]["repo_slug"] == "demo-fam"
    assert "repo_root" not in manifest["_generated"]
    # template_repo is intentionally an absolute path (B2 fix: preserved verbatim).
    # Strip it before checking that no other host-absolute paths leaked.
    import copy as _copy
    manifest_no_template = _copy.deepcopy(manifest)
    if "template_parity" in manifest_no_template.get("rule_inputs", {}):
        manifest_no_template["rule_inputs"]["template_parity"].pop("template_repo", None)
    dumped_no_template = json.dumps(manifest_no_template)
    assert "/Volumes" not in dumped_no_template, (
        "host-absolute /Volumes path leaked into generated manifest (excluding template_repo)"
    )
    assert "/Users/" not in dumped_no_template, (
        "host-absolute /Users/ path leaked into generated manifest (excluding template_repo)"
    )
    assert render_args == [
        "--family",
        "demo-fam",
        "--dry-run",
        "--target",
        "role-policy",
    ]
    assert "mir-harness" not in render_args


def test_build_manifest_green_real_repo_runs_pass() -> None:
    manifest = build_manifest(
        PROJECT_ROOT,
        PROJECT_ROOT / "config" / "repos" / "mir-yoke.json",
        green=True,
    )

    result = run_with_manifest(PROJECT_ROOT, manifest)
    enabled_error_rule_ids = {
        rule["id"]
        for rule in manifest["rules"]
        if rule["enabled"] and rule["severity"] == "ERROR"
    }
    error_finding_rule_ids = {
        finding["rule_id"]
        for finding in result["findings"]
        if finding["severity"] == "ERROR"
    }

    jsonschema.validate(instance=manifest, schema=_schema())
    assert result["overall"] == "pass"
    assert enabled_error_rule_ids.isdisjoint(error_finding_rule_ids)


def test_build_manifest_green_minimal_repo_disables_missing_prerequisites(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "profile.json"
    _write_json(
        profile_path,
        {
            "slug": "minimal",
            "repository_type": "code_app",
        },
    )

    manifest = build_manifest(tmp_path, profile_path, green=True)
    result = run_with_manifest(tmp_path, manifest)
    disabled_rule_ids = {
        disabled_rule["rule_id"]
        for disabled_rule in manifest["_generated"]["disabled_rules"]
    }

    assert result["overall"] == "pass"
    assert disabled_rule_ids >= {"R2", "R5"}


def test_run_with_manifest_matches_run_for_committed_manifest() -> None:
    manifest = json.loads(
        (PROJECT_ROOT / "config" / "harness-consistency.json").read_text(
            encoding="utf-8",
        )
    )

    assert run_with_manifest(PROJECT_ROOT, manifest) == run(PROJECT_ROOT)


def test_generate_parser_accepts_green_flag() -> None:
    args = build_parser().parse_args(
        [
            "generate",
            "--green",
            "--repo-root",
            ".",
            "--profile",
            "config/repos/mir-harness.json",
        ]
    )

    assert args.green is True


# ---------------------------------------------------------------------------
# B2: template_repo preservation in _build_rule_inputs (ADR-54 S2 D2)
# ---------------------------------------------------------------------------

_STUB_SOURCE_INPUTS = {
    # _DIRECT_STATIC_INPUTS keys (all required by _build_rule_inputs)
    "adr_status_enum": {},
    "settings_dual_fire_dedup": {},
    "single_family_source": {},
    "catalog_loader_usage": {},
    "adr_supersession_graph": {},
    "context_path_references": {},
    "architecture_contract": {},
    "generated_marker_rerender": {
        "surfaces": [],
        "marker": "mir:generated",
        "generator": "x",
    },
    # Other required keys consumed by _build_rule_inputs
    "removed_symbol_references": {
        "scan_dirs": [],
        "file_globs": [],
        "allowed_path_substrings": [],
    },
    "hook_file_reachability": {
        "hooks_dir": ".claude/hooks",
        "file_globs": [],
        "settings_files": [],
        "archive_exclude": [],
    },
    "archived_source_phase_doc": {
        "hook_archive_dir": ".archive/hooks",
        "settings_files": [],
        "phase_doc_globs": [],
        "live_claim_keywords": [],
        "exempt_token": "",
    },
    "hook_tier_declaration": {
        "hooks_dir": ".claude/hooks",
        "marker_prefix": "tier:",
    },
}


def test_build_rule_inputs_non_template_keeps_abs_template_repo(tmp_path: Path) -> None:
    """B2a: non-template family gets verbatim abs template_repo from source_inputs."""
    from tools.harness_consistency.generate import _build_rule_inputs

    abs_template = str(tmp_path / "template-root")
    source_inputs = {
        **_STUB_SOURCE_INPUTS,
        "template_parity": {
            "template_repo": abs_template,
            "manifest_path": "config/parity-manifest.json",
            "probes_enabled": True,
            "exclude_paths": [".claude/hooks/session-start.sh"],
        },
    }

    result = _build_rule_inputs(
        tmp_path,
        source_inputs,
        source_slug="mir-harness",
        target_slug="some-family",
    )

    assert "template_parity" in result
    tp = result["template_parity"]
    # Non-template target must keep verbatim absolute path from source
    assert tp["template_repo"] == abs_template, (
        f"Expected verbatim abs path {abs_template!r}, got {tp['template_repo']!r}"
    )
    # source-repo exclude_paths must NOT be inherited by non-mir target
    assert "exclude_paths" not in tp, (
        f"source-repo exclude_paths must be stripped for non-source targets, got {tp}"
    )


def test_build_rule_inputs_template_target_gets_dot_template_repo(tmp_path: Path) -> None:
    """B2b: mir-yoke target gets template_repo == "." (self-referential)."""
    from tools.harness_consistency.generate import _build_rule_inputs

    abs_template = str(tmp_path / "template-root")
    source_inputs = {
        **_STUB_SOURCE_INPUTS,
        "template_parity": {
            "template_repo": abs_template,
            "manifest_path": "config/parity-manifest.json",
            "probes_enabled": True,
            "exclude_paths": [".claude/hooks/session-start.sh"],
        },
    }

    result = _build_rule_inputs(
        tmp_path,
        source_inputs,
        source_slug="mir-harness",
        target_slug="mir-yoke",
    )

    assert "template_parity" in result
    tp = result["template_parity"]
    # Template target must use "." so checker resolves against its own root
    assert tp["template_repo"] == ".", (
        f"Expected template_repo == '.', got {tp['template_repo']!r}"
    )


def test_build_manifest_rule_inputs_contains_agent_surface_contract(
    tmp_path: Path,
) -> None:
    from tools.harness_consistency.generate import _build_rule_inputs

    agent_surface_contract = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [".claude/settings.json", ".claude/settings.local.json"],
        "agents_md": "AGENTS.md",
        "memory_marker": "mir:generated",
        "marker_surfaces": ["docs/memory-map.md", "tasks/lessons.md"],
        "mirror_heading": "## Memory (DB-canonical",
    }
    source_inputs = {
        **_STUB_SOURCE_INPUTS,
        "agent_surface_contract": agent_surface_contract,
    }

    result = _build_rule_inputs(
        tmp_path,
        source_inputs,
        source_slug="mir-harness",
        target_slug="some-family",
    )

    assert "agent_surface_contract" in result
    expected_keys = {
        "claude_md",
        "agents_dir",
        "skills_dir",
        "settings_files",
        "agents_md",
        "memory_marker",
        "marker_surfaces",
        "mirror_heading",
    }
    assert expected_keys <= result["agent_surface_contract"].keys()


def test_build_manifest_real_repo_rule_inputs_has_agent_surface_contract() -> None:
    manifest = build_manifest(
        PROJECT_ROOT,
        PROJECT_ROOT / "config" / "repos" / "mir-yoke.json",
    )

    assert "agent_surface_contract" in manifest["rule_inputs"]
    expected_keys = {
        "claude_md",
        "agents_dir",
        "settings_files",
    }
    assert expected_keys <= manifest["rule_inputs"]["agent_surface_contract"].keys()
