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


def test_build_manifest_real_repo_section_and_rules() -> None:
    manifest = build_manifest(
        PROJECT_ROOT,
        PROJECT_ROOT / "config" / "repos" / "mir-yoke.json",
    )

    assert manifest["repo"] == {
        "slug": "mir-yoke",
        "repository_type": "public_harness_template",
        "role": "template_maintainer",
        "enforcement": {
            "tools_commit_gate": "lint_test",
            "tools_tdd_ledger": "changes_array",
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


def test_build_manifest_never_infers_fleet_authority(tmp_path: Path) -> None:
    profile_path = tmp_path / "config" / "repos" / "app.json"
    _write_json(
        profile_path,
        {
            "slug": "app",
            "repository_type": "code_app",
            "fleet_management": {"control_repo": True},
        },
    )

    manifest = build_manifest(tmp_path, profile_path)

    assert manifest["repo"]["role"] == "code_tdd_review_plane"
    assert "fleet_manager" not in manifest["repo"]
    assert manifest["repo"]["enforcement"] == {
        "tools_commit_gate": "lint_test",
        "tools_tdd_ledger": "changes_array",
    }


def test_build_manifest_localizes_metadata_without_private_profile_rendering(
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
    assert manifest["_generated"]["repo_slug"] == "demo-fam"
    assert "repo_root" not in manifest["_generated"]
    dumped_no_template = json.dumps(manifest)
    assert "/" + "Volumes" not in dumped_no_template, (
        "host-absolute /Volumes path leaked into generated manifest (excluding template_repo)"
    )
    assert "/" + "Users/" not in dumped_no_template, (
        "host-absolute user path leaked into generated manifest"
    )
    surfaces = manifest["rule_inputs"]["generated_marker_rerender"]["surfaces"]
    assert all(surface["file"] != "CLAUDE.md" for surface in surfaces)


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
# Rule-input localization
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
    "template_asset_classification": {"manifest_path": "config/template-assets.json"},
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


def test_build_rule_inputs_keeps_local_asset_manifest(tmp_path: Path) -> None:
    from tools.harness_consistency.generate import _build_rule_inputs

    result = _build_rule_inputs(
        tmp_path,
        _STUB_SOURCE_INPUTS,
        source_slug="mir-harness",
        target_slug="some-family",
    )

    assert result["template_asset_classification"] == {
        "manifest_path": "config/template-assets.json"
    }


def test_build_manifest_rule_inputs_contains_agent_surface_contract(
    tmp_path: Path,
) -> None:
    from tools.harness_consistency.generate import _build_rule_inputs

    agent_surface_contract = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dirs": [
            "plugins/mir-core/skills",
            "plugins/mir-code/skills",
            "plugins/mir-content/skills",
        ],
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
        "skills_dirs",
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
