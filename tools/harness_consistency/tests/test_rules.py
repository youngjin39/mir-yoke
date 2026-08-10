from __future__ import annotations

import json
from pathlib import Path

from tools.harness_consistency.rules import (
    adopter_payload_boundary,
    adr_artifact_present,
    adr_status_enum,
    adr_supersession_graph,
    architecture_contract,
    archived_source_phase_doc,
    catalog_loader_usage,
    code_schema_constraint_agreement,
    context_path_references,
    generated_marker_rerender,
    hook_file_reachability,
    hook_tier_declaration,
    removed_symbol_references,
    settings_dual_fire_dedup,
    single_family_source,
    wired_gate_liveness,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _manifest_inputs(rule_name: str) -> dict:
    manifest = json.loads(
        (PROJECT_ROOT / "config" / "harness-consistency.json").read_text(encoding="utf-8")
    )
    return manifest["rule_inputs"][rule_name]


def _write_repo_profile(path: Path, *, slug: str, repository_type: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[repo]\n"
        f'slug = "{slug}"\n'
        f'repository_type = "{repository_type}"\n',
        encoding="utf-8",
    )


_ADOPTER_BOUNDARY_INPUTS = {"boundary_manifest_path": "config/adopter-boundary.json"}


def _write_adopter_boundary(root: Path) -> None:
    _write_json(
        root / "config/adopter-boundary.json",
        {
            "schema_version": 1,
            "provider_owners": [
                {
                    "slug": "mir-yoke",
                    "repository_types": [
                        "public_harness_template",
                        "template_transitional",
                    ],
                }
            ],
            "provider_markers": [
                ".agents/plugins/marketplace.json",
                "src/mir",
                "plugins/mir-core",
                "tools/harness_consistency",
                "tests/test_template_asset_classification.py",
                "config/template-assets.json",
            ],
            "provider_text_markers": [],
            "source_asset_manifest": "config/template-assets.json",
            "payload_manifest": "config/adopter-payload.json",
            "remove_classifications": ["template-maintainer-tool"],
        },
    )


def test_should_return_blocking_findings_when_adopter_retains_provider_tree(
    tmp_path: Path,
) -> None:
    _write_adopter_boundary(tmp_path)
    _write_repo_profile(
        tmp_path / ".mir/repo-profile.toml",
        slug="sample-product",
        repository_type="starter_project",
    )
    (tmp_path / "src/mir").mkdir(parents=True)
    (tmp_path / "tools/harness_consistency").mkdir(parents=True)
    marketplace = tmp_path / ".agents/plugins/marketplace.json"
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text("{}\n", encoding="utf-8")

    findings = adopter_payload_boundary(tmp_path, _ADOPTER_BOUNDARY_INPUTS)

    assert [finding.location for finding in findings] == [
        ".agents/plugins/marketplace.json",
        "src/mir",
        "tools/harness_consistency",
    ]
    assert all(finding.rule_id == "R20" for finding in findings)
    assert all(finding.severity == "ERROR" for finding in findings)
    assert all("complete greenfield Phase 2 finalize" in finding.message for finding in findings)


def test_should_return_no_findings_when_provider_owner_retains_development_tree(
    tmp_path: Path,
) -> None:
    _write_adopter_boundary(tmp_path)
    _write_repo_profile(
        tmp_path / ".mir/repo-profile.toml",
        slug="mir-yoke",
        repository_type="public_harness_template",
    )
    (tmp_path / "src/mir").mkdir(parents=True)
    (tmp_path / "tools/harness_consistency").mkdir(parents=True)

    assert adopter_payload_boundary(tmp_path, _ADOPTER_BOUNDARY_INPUTS) == []


def test_should_return_no_findings_when_adopter_payload_is_slim(tmp_path: Path) -> None:
    _write_adopter_boundary(tmp_path)
    _write_repo_profile(
        tmp_path / ".mir/repo-profile.toml",
        slug="sample-product",
        repository_type="starter_project",
    )
    (tmp_path / "apps").mkdir()
    (tmp_path / ".ai-harness").mkdir()

    assert adopter_payload_boundary(tmp_path, _ADOPTER_BOUNDARY_INPUTS) == []


def test_adr_status_enum_reports_invalid_status(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema" / "adr.schema.json"
    _write_json(schema_path, {"frontmatter_status_enum": ["accepted", "proposed"]})

    adr_dir = tmp_path / "docs" / "decisions"
    adr_dir.mkdir(parents=True)
    (adr_dir / "adr-001-valid.md").write_text(
        "---\nstatus: accepted\n---\n# Valid\n",
        encoding="utf-8",
    )
    (adr_dir / "adr-002-invalid.md").write_text(
        "---\nstatus: bogus\n---\n# Invalid\n",
        encoding="utf-8",
    )

    findings = adr_status_enum(
        tmp_path,
        {
            "adr_glob": "docs/decisions/adr-*.md",
            "enum_schema": "schema/adr.schema.json",
            "enum_key": "frontmatter_status_enum",
        },
    )

    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].rule_id == "R5"
    assert findings[0].location == "docs/decisions/adr-002-invalid.md: bogus"


def test_adr_status_enum_reports_missing_enum_key(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema" / "adr.schema.json"
    _write_json(schema_path, {"other_enum": ["accepted"]})

    findings = adr_status_enum(
        tmp_path,
        {
            "adr_glob": "docs/decisions/adr-*.md",
            "enum_schema": "schema/adr.schema.json",
            "enum_key": "frontmatter_status_enum",
        },
    )

    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].message == "status enum source missing: frontmatter_status_enum"


def test_single_family_source_reports_missing_required_symbol(tmp_path: Path) -> None:
    source = tmp_path / "tools" / "profile_compiler" / "cli.py"
    source.parent.mkdir(parents=True)
    source.write_text("FAMILY_REGISTRY = {}\n", encoding="utf-8")

    findings = single_family_source(
        tmp_path,
        {
            "source_files": ["tools/profile_compiler/cli.py"],
            "required_symbol": "load_family_registry",
        },
    )

    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].rule_id == "R3"
    assert findings[0].location == "tools/profile_compiler/cli.py"


def test_single_family_source_allows_required_symbol(tmp_path: Path) -> None:
    source = tmp_path / "tools" / "profile_compiler" / "cli.py"
    source.parent.mkdir(parents=True)
    source.write_text("from tools.catalog_loader import load_family_registry\n", encoding="utf-8")

    findings = single_family_source(
        tmp_path,
        {
            "source_files": ["tools/profile_compiler/cli.py"],
            "required_symbol": "load_family_registry",
        },
    )

    assert findings == []


def test_catalog_loader_usage_reports_repository_index_without_loader(tmp_path: Path) -> None:
    source = tmp_path / "tools" / "consumer.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "def slugs(manifest):\n    return manifest['repositories']\n",
        encoding="utf-8",
    )

    findings = catalog_loader_usage(
        tmp_path,
        {"scan_dirs": ["tools"], "exclude_substrings": ["catalog_loader.py"]},
    )

    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].rule_id == "R4"
    assert findings[0].location == "tools/consumer.py"


def test_catalog_loader_usage_allows_repository_index_with_loader(tmp_path: Path) -> None:
    source = tmp_path / "tools" / "consumer.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from tools.catalog_loader import load_catalog\n"
        "def slugs(root):\n"
        "    manifest = load_catalog(root)\n"
        "    return manifest[\"repositories\"]\n",
        encoding="utf-8",
    )

    findings = catalog_loader_usage(
        tmp_path,
        {"scan_dirs": ["tools"], "exclude_substrings": ["catalog_loader.py"]},
    )

    assert findings == []


def test_adr_supersession_graph_reports_graph_violations(tmp_path: Path) -> None:
    adr_dir = tmp_path / "docs" / "decisions"
    adr_dir.mkdir(parents=True)
    (adr_dir / "adr-01-source.md").write_text(
        "---\nstatus: accepted\nsupersedes: adr-99-missing\n---\n# Source\n",
        encoding="utf-8",
    )
    (adr_dir / "adr-02-source.md").write_text(
        "---\nstatus: accepted\nsupersedes: [adr-03-target]\n---\n# Source\n",
        encoding="utf-8",
    )
    (adr_dir / "adr-03-target.md").write_text(
        "---\nstatus: superseded\n---\n# Target\n",
        encoding="utf-8",
    )
    (adr_dir / "adr-04-accepted-superseded.md").write_text(
        "---\nstatus: accepted\nsuperseded_by: adr-02\n---\n# Bad\n",
        encoding="utf-8",
    )

    findings = adr_supersession_graph(
        tmp_path,
        {"adr_glob": "docs/decisions/adr-*.md"},
    )

    messages = [finding.message for finding in findings]
    assert "ADR supersedes missing target: adr-99-missing" in messages
    assert "ADR supersession missing reciprocal superseded_by" in messages
    assert "ADR is accepted but has superseded_by" in messages
    assert len(findings) == 3


def test_adr_supersession_graph_allows_reciprocal_graph(tmp_path: Path) -> None:
    adr_dir = tmp_path / "docs" / "decisions"
    adr_dir.mkdir(parents=True)
    (adr_dir / "adr-01-old.md").write_text(
        "---\nstatus: superseded\nsuperseded_by: adr-02-new.md\n---\n# Old\n",
        encoding="utf-8",
    )
    (adr_dir / "adr-02-new.md").write_text(
        "---\nstatus: accepted\nsupersedes:\n  - adr-01\n---\n# New\n",
        encoding="utf-8",
    )

    findings = adr_supersession_graph(
        tmp_path,
        {"adr_glob": "docs/decisions/adr-*.md"},
    )

    assert findings == []


def test_context_path_references_reports_nonzero_script(tmp_path: Path) -> None:
    script = tmp_path / "fail_context.py"
    script.write_text(
        "import sys\n"
        "print('line 1')\n"
        "print('line 2')\n"
        "print('line 3')\n"
        "print('line 4')\n"
        "print('line 5')\n"
        "print('line 6')\n"
        "print('bad context', file=sys.stderr)\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )

    findings = context_path_references(
        tmp_path,
        {"script": "fail_context.py", "args": []},
    )

    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].rule_id == "R2"
    assert "line 2" not in findings[0].message
    assert "bad context" in findings[0].message


def test_context_path_references_allows_zero_script(tmp_path: Path) -> None:
    script = tmp_path / "ok_context.py"
    script.write_text("raise SystemExit(0)\n", encoding="utf-8")

    findings = context_path_references(
        tmp_path,
        {"script": "ok_context.py", "args": []},
    )

    assert findings == []


def test_architecture_contract_reports_nonzero_module(tmp_path: Path) -> None:
    module = tmp_path / "failing_contract.py"
    module.write_text(
        "import sys\n"
        "print('contract drift')\n"
        "print(sys.argv[1])\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )

    findings = architecture_contract(
        tmp_path,
        {"module": "failing_contract", "subcommand": "check"},
    )

    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].rule_id == "R13"
    assert "contract drift" in findings[0].message
    assert "check" in findings[0].message


def test_architecture_contract_allows_zero_module(tmp_path: Path) -> None:
    module = tmp_path / "passing_contract.py"
    module.write_text("raise SystemExit(0)\n", encoding="utf-8")

    findings = architecture_contract(
        tmp_path,
        {"module": "passing_contract", "subcommand": "check"},
    )

    assert findings == []


def test_settings_dual_fire_dedup_reports_shared_event_command(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "settings.json",
        {"hooks": {"PreToolUse": [{"hooks": [{"command": "python hook.py"}]}]}},
    )
    _write_json(
        tmp_path / "settings.local.json",
        {"hooks": {"PreToolUse": [{"hooks": [{"command": "python hook.py"}]}]}},
    )

    findings = settings_dual_fire_dedup(
        tmp_path,
        {"settings_files": ["settings.json", "settings.local.json"]},
    )

    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].rule_id == "R10"
    assert "PreToolUse" in findings[0].location
    assert "python hook.py" in findings[0].location


def test_settings_dual_fire_dedup_allows_disjoint_commands(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "settings.json",
        {"hooks": {"PreToolUse": [{"hooks": [{"command": "python one.py"}]}]}},
    )
    _write_json(
        tmp_path / "settings.local.json",
        {"hooks": {"PreToolUse": [{"hooks": [{"command": "python two.py"}]}]}},
    )

    findings = settings_dual_fire_dedup(
        tmp_path,
        {"settings_files": ["settings.json", "settings.local.json"]},
    )

    assert findings == []


def test_removed_symbol_references_real_repo_green() -> None:
    findings = removed_symbol_references(
        PROJECT_ROOT,
        _manifest_inputs("removed_symbol_references"),
    )

    assert findings == []


def test_removed_symbol_references_reports_retired_symbol(tmp_path: Path) -> None:
    source = tmp_path / "tools" / "live.py"
    source.parent.mkdir(parents=True)
    source.write_text("STATE = 'active_task.json'\n", encoding="utf-8")

    findings = removed_symbol_references(
        tmp_path,
        {
            "scan_dirs": ["tools"],
            "file_globs": ["*.py"],
            "retired_symbols": ["active_task.json"],
            "allowed_path_substrings": [],
        },
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "R1"
    assert findings[0].severity == "ERROR"
    assert findings[0].location == "tools/live.py: active_task.json"


def test_hook_file_reachability_real_repo_green() -> None:
    findings = hook_file_reachability(
        PROJECT_ROOT,
        _manifest_inputs("hook_file_reachability"),
    )

    assert findings == []


def test_hook_file_reachability_reports_orphan_hook(tmp_path: Path) -> None:
    hook = tmp_path / ".claude" / "hooks" / "orphan.sh"
    hook.parent.mkdir(parents=True)
    hook.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    _write_json(tmp_path / ".claude" / "settings.json", {"hooks": {}})

    findings = hook_file_reachability(
        tmp_path,
        {
            "hooks_dir": ".claude/hooks",
            "file_globs": ["*.sh"],
            "settings_files": [".claude/settings.json"],
            "archive_exclude": ".claude/hooks/archive/",
            "manual_trigger_allowlist": [],
        },
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "R8"
    assert findings[0].severity == "ERROR"
    assert findings[0].location == ".claude/hooks/orphan.sh"


def test_wired_gate_liveness_real_repo_green() -> None:
    findings = wired_gate_liveness(
        PROJECT_ROOT,
        _manifest_inputs("wired_gate_liveness"),
    )

    assert findings == []


def test_wired_gate_liveness_reports_missing_dependency(tmp_path: Path) -> None:
    findings = wired_gate_liveness(
        tmp_path,
        {"gates": [{"hook": ".claude/hooks/pre-tool-use.sh", "requires_path": "missing.py"}]},
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "R12"
    assert findings[0].severity == "ERROR"
    assert findings[0].location == ".claude/hooks/pre-tool-use.sh -> missing.py"


def test_archived_source_phase_doc_real_repo_green() -> None:
    findings = archived_source_phase_doc(
        PROJECT_ROOT,
        _manifest_inputs("archived_source_phase_doc"),
    )

    assert findings == []


def test_archived_source_phase_doc_reports_stale_phase_claim(tmp_path: Path) -> None:
    phase_doc = tmp_path / "docs" / "harness-engineering" / "phase-1.md"
    phase_doc.parent.mkdir(parents=True)
    phase_doc.write_text("we land design-complete-gate.sh in this phase\n", encoding="utf-8")

    findings = archived_source_phase_doc(
        tmp_path,
        {
            "hook_archive_dir": ".claude/hooks/archive",
            "settings_files": [],
            "phase_doc_globs": ["docs/harness-engineering/phase-*.md"],
            "archived_hook_names": ["design-complete-gate"],
            "live_claim_keywords": ["land"],
            "exempt_token": "ARCHIVED",
        },
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "R14"
    assert findings[0].severity == "ERROR"
    assert findings[0].location == "docs/harness-engineering/phase-1.md:1"


def test_code_schema_constraint_agreement_real_repo_green() -> None:
    findings = code_schema_constraint_agreement(
        PROJECT_ROOT,
        _manifest_inputs("code_schema_constraint_agreement"),
    )

    assert findings == []


def test_code_schema_constraint_agreement_reports_mismatch(tmp_path: Path) -> None:
    python_file = tmp_path / "tools" / "profile_compiler" / "bootstrap.py"
    python_file.parent.mkdir(parents=True)
    python_file.write_text("if len(managed_domains) < 7:\n    pass\n", encoding="utf-8")
    _write_json(
        tmp_path / "schema.json",
        {"properties": {"managed_domains": {"type": "array", "minItems": 6}}},
    )

    findings = code_schema_constraint_agreement(
        tmp_path,
        {
            "pairs": [
                {
                    "python_file": "tools/profile_compiler/bootstrap.py",
                    "python_regex": r"managed_domains\)\s*<\s*(\d+)",
                    "schema_file": "schema.json",
                    "schema_field": "managed_domains",
                    "schema_key": "minItems",
                }
            ]
        },
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "R15"
    assert findings[0].severity == "ERROR"
    assert "7 vs schema.json managed_domains.minItems 6" in findings[0].message


def test_adr_artifact_present_real_repo_green() -> None:
    findings = adr_artifact_present(
        PROJECT_ROOT,
        _manifest_inputs("adr_artifact_present"),
    )

    assert findings == []


def test_adr_artifact_present_reports_missing_artifact(tmp_path: Path) -> None:
    findings = adr_artifact_present(
        tmp_path,
        {"artifact_map": {"adr-99": "missing/artifact"}},
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "R7"
    assert findings[0].severity == "WARN"
    assert findings[0].location == "missing/artifact"


def test_hook_tier_declaration_real_repo_green() -> None:
    findings = hook_tier_declaration(
        PROJECT_ROOT,
        _manifest_inputs("hook_tier_declaration"),
    )

    assert findings == []


def test_hook_tier_declaration_reports_missing_expected_tier(tmp_path: Path) -> None:
    hook = tmp_path / ".claude" / "hooks" / "pre-tool-use.sh"
    hook.parent.mkdir(parents=True)
    hook.write_text('_MIR_HOOK_TIER="warn"\n', encoding="utf-8")

    findings = hook_tier_declaration(
        tmp_path,
        {
            "hooks_dir": ".claude/hooks",
            "marker_prefix": "_MIR_HOOK_TIER",
            "expected_tiers": {"pre-tool-use.sh": "block"},
        },
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "R9"
    assert findings[0].severity == "WARN"
    assert findings[0].location == "pre-tool-use.sh"


def test_generated_marker_rerender_real_repo_green_or_warn_only() -> None:
    findings = generated_marker_rerender(
        PROJECT_ROOT,
        _manifest_inputs("generated_marker_rerender"),
    )

    assert all(finding.rule_id == "R11" for finding in findings)
    assert all(finding.severity == "WARN" for finding in findings)


def test_generated_marker_rerender_reports_drift(tmp_path: Path) -> None:
    marker_begin = "<!-- generated:start -->"
    marker_end = "<!-- generated:end -->"
    (tmp_path / "surface.md").write_text(
        f"{marker_begin}\ncommitted\n{marker_end}\n",
        encoding="utf-8",
    )
    (tmp_path / "source.db").write_text("present\n", encoding="utf-8")
    (tmp_path / "stub_render.py").write_text(
        "print('<!-- generated:start -->')\n"
        "print('fresh')\n"
        "print('<!-- generated:end -->')\n",
        encoding="utf-8",
    )

    findings = generated_marker_rerender(
        tmp_path,
        {
            "surfaces": [
                {
                    "file": "surface.md",
                    "marker_begin": marker_begin,
                    "marker_end": marker_end,
                    "render_module": "stub_render",
                    "render_args": [],
                    "source": "source.db",
                    "skip_if_source_absent": True,
                }
            ]
        },
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "R11"
    assert findings[0].severity == "WARN"
    assert findings[0].location == "surface.md"


# ---------------------------------------------------------------------------
# R17 agent_surface_contract
# ---------------------------------------------------------------------------

def _write_text_r17(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_exec_r17(path, content):
    _write_text_r17(path, content)
    path.chmod(0o755)


def _write_json_r17(path, data):
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _make_clean_r17_repo(tmp_path):
    root = tmp_path / "clean_repo"
    _write_text_r17(
        root / "CLAUDE.md",
        "- `tasks/plan.md`\n- `docs/decisions/adr-01.md`\n",
    )
    _write_text_r17(root / "tasks" / "plan.md", "")
    _write_text_r17(root / "docs" / "decisions" / "adr-01.md", "")
    hook = root / ".claude" / "hooks" / "pre-tool-use.sh"
    _write_exec_r17(hook, "#!/bin/bash\necho ok")
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": ".claude/hooks/pre-tool-use.sh",
                        }
                    ],
                }
            ]
        }
    }
    _write_json_r17(root / ".claude" / "settings.json", settings)
    _write_text_r17(
        root / ".claude" / "agents" / "my-agent.md",
        "---\nname: my-agent\n---\n# body",
    )
    _write_text_r17(root / ".claude" / "skills" / "my-skill" / "SKILL.md", "# skill")
    _write_text_r17(root / "AGENTS.md", "## Memory (DB-canonical -- ADR-50)\nsome text")
    _write_text_r17(
        root / "docs" / "memory-map.md",
        "<!-- mir:generated:start -->\nstuff\n<!-- mir:generated:end -->",
    )
    return root


def test_r17_clean_repo_no_findings(tmp_path):
    """Clean repo produces zero R17 findings."""
    from tools.harness_consistency.rules import agent_surface_contract
    root = _make_clean_r17_repo(tmp_path)
    rule_inputs = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [".claude/settings.json"],
        "agents_md": "AGENTS.md",
        "memory_marker": "mir:generated",
        "marker_surfaces": ["docs/memory-map.md"],
        "mirror_heading": "## Memory (DB-canonical",
    }
    findings = agent_surface_contract(root, rule_inputs)
    assert findings == [], (
        f"Expected no findings for clean repo, got: {findings}"
    )


def test_r17_missing_cited_path(tmp_path):
    """cited_paths: slashed .md path in CLAUDE.md that does not exist triggers finding."""
    from tools.harness_consistency.rules import agent_surface_contract
    root = tmp_path / "cited_gap"
    root.mkdir()
    _write_text_r17(root / "CLAUDE.md", "see `tasks/missing-file.md`")
    rule_inputs = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [],
        "agents_md": "AGENTS.md",
        "memory_marker": "mir:generated",
        "marker_surfaces": [],
        "mirror_heading": "## Memory (DB-canonical",
    }
    findings = agent_surface_contract(root, rule_inputs)
    cited = [f for f in findings if "tasks/missing-file.md" in f.message]
    assert len(cited) >= 1, f"Expected cited_paths finding, got: {findings}"
    assert all(f.rule_id == "R17" for f in findings)


def test_r17_generated_cited_path_may_be_absent_before_bootstrap(tmp_path):
    """cited_paths: a declared post-bootstrap local file may be absent in a clean template."""
    from tools.harness_consistency.rules import agent_surface_contract

    root = tmp_path / "generated_citation"
    root.mkdir()
    _write_text_r17(root / "CLAUDE.md", "after bootstrap read `.mir/repo-profile.toml`")
    rule_inputs = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [],
        "agents_md": "AGENTS.md",
        "generated_cited_paths": [".mir/repo-profile.toml"],
        "memory_marker": "mir:generated",
        "marker_surfaces": [],
        "mirror_heading": "## Memory (DB-canonical",
    }

    findings = agent_surface_contract(root, rule_inputs)

    assert [finding for finding in findings if "cited_paths" in finding.message] == []


def test_r17_bare_filename_not_flagged(tmp_path):
    """cited_paths: bare filename without slash must NOT produce finding."""
    from tools.harness_consistency.rules import agent_surface_contract
    root = tmp_path / "bare_name"
    root.mkdir()
    _write_text_r17(root / "CLAUDE.md", "read `CLAUDE.md` and `README.md` first")
    rule_inputs = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [],
        "agents_md": "AGENTS.md",
        "memory_marker": "mir:generated",
        "marker_surfaces": [],
        "mirror_heading": "## Memory (DB-canonical",
    }
    findings = agent_surface_contract(root, rule_inputs)
    assert findings == [], f"Bare filenames must not produce findings, got: {findings}"


def test_r17_missing_hook_script(tmp_path):
    """hook_scripts: settings.json referencing a missing script triggers ERROR finding."""
    import json

    from tools.harness_consistency.rules import agent_surface_contract

    root = tmp_path / "hook_gap"
    root.mkdir()
    _write_text_r17(root / "CLAUDE.md", "")
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": ".claude/hooks/dead-hook.sh",
                        }
                    ],
                }
            ]
        }
    }
    sp = root / ".claude" / "settings.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(settings), encoding="utf-8")
    rule_inputs = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [".claude/settings.json"],
        "agents_md": "AGENTS.md",
        "memory_marker": "mir:generated",
        "marker_surfaces": [],
        "mirror_heading": "## Memory (DB-canonical",
    }
    findings = agent_surface_contract(root, rule_inputs)
    hook_findings = [f for f in findings if "dead-hook.sh" in f.message]
    assert len(hook_findings) >= 1, f"Expected hook_scripts finding, got: {findings}"
    assert hook_findings[0].severity == "ERROR"


def test_r17_bash_prefixed_nonexec_not_flagged(tmp_path):
    """hook_scripts: 'bash hook.sh' (interpreter-prefixed) must not require exec bit."""
    import json

    from tools.harness_consistency.rules import agent_surface_contract

    root = tmp_path / "bash_prefix"
    root.mkdir()
    _write_text_r17(root / "CLAUDE.md", "")
    hook = root / ".claude" / "hooks" / "my-hook.sh"
    _write_text_r17(hook, "#!/bin/bash\necho ok")
    settings = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "bash .claude/hooks/my-hook.sh",
                        }
                    ],
                }
            ]
        }
    }
    sp = root / ".claude" / "settings.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(settings), encoding="utf-8")
    rule_inputs = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [".claude/settings.json"],
        "agents_md": "AGENTS.md",
        "memory_marker": "mir:generated",
        "marker_surfaces": [],
        "mirror_heading": "## Memory (DB-canonical",
    }
    findings = agent_surface_contract(root, rule_inputs)
    assert findings == [], (
        f"bash-prefixed hook must not require exec bit, got: {findings}"
    )


def test_r17_agent_missing_frontmatter(tmp_path):
    """agents_frontmatter: agent .md without frontmatter block triggers finding."""
    from tools.harness_consistency.rules import agent_surface_contract
    root = tmp_path / "agent_gap"
    root.mkdir()
    _write_text_r17(root / "CLAUDE.md", "")
    _write_text_r17(root / ".claude" / "agents" / "broken-agent.md", "# no frontmatter here")
    rule_inputs = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [],
        "agents_md": "AGENTS.md",
        "memory_marker": "mir:generated",
        "marker_surfaces": [],
        "mirror_heading": "## Memory (DB-canonical",
    }
    findings = agent_surface_contract(root, rule_inputs)
    agent_findings = [
        f
        for f in findings
        if "broken-agent.md" in f.message
        or "broken-agent.md" in f.location
    ]
    assert len(agent_findings) >= 1, (
        f"Expected agents_frontmatter finding, got: {findings}"
    )


def test_r17_readme_agent_not_flagged(tmp_path):
    """agents_frontmatter: README*.md in agents/ must be excluded."""
    from tools.harness_consistency.rules import agent_surface_contract
    root = tmp_path / "readme_skip"
    root.mkdir()
    _write_text_r17(root / "CLAUDE.md", "")
    _write_text_r17(root / ".claude" / "agents" / "README.md", "# no frontmatter")
    rule_inputs = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [],
        "agents_md": "AGENTS.md",
        "memory_marker": "mir:generated",
        "marker_surfaces": [],
        "mirror_heading": "## Memory (DB-canonical",
    }
    findings = agent_surface_contract(root, rule_inputs)
    assert findings == [], f"README in agents/ must not be flagged, got: {findings}"


def test_r17_skill_missing_skill_md(tmp_path):
    """skills_structure: skill dir without SKILL.md triggers finding."""
    from tools.harness_consistency.rules import agent_surface_contract
    root = tmp_path / "skill_gap"
    root.mkdir()
    _write_text_r17(root / "CLAUDE.md", "")
    (root / ".claude" / "skills" / "my-skill").mkdir(parents=True, exist_ok=True)
    rule_inputs = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [],
        "agents_md": "AGENTS.md",
        "memory_marker": "mir:generated",
        "marker_surfaces": [],
        "mirror_heading": "## Memory (DB-canonical",
    }
    findings = agent_surface_contract(root, rule_inputs)
    skill_findings = [
        f
        for f in findings
        if "my-skill" in f.message
        or "my-skill" in f.location
    ]
    assert len(skill_findings) >= 1, (
        f"Expected skills_structure finding, got: {findings}"
    )


def test_r17_plugin_skill_roots_are_all_checked(tmp_path):
    """skills_structure checks every configured namespaced plugin root."""
    from tools.harness_consistency.rules import agent_surface_contract

    root = tmp_path / "plugin_skill_gap"
    root.mkdir()
    _write_text_r17(root / "CLAUDE.md", "")
    _write_text_r17(
        root / "plugins" / "mir-core" / "skills" / "design" / "SKILL.md",
        "# design",
    )
    (root / "plugins" / "mir-content" / "skills" / "knowledge").mkdir(
        parents=True,
        exist_ok=True,
    )
    findings = agent_surface_contract(
        root,
        {
            "claude_md": "CLAUDE.md",
            "agents_dir": ".claude/agents",
            "skills_dirs": [
                "plugins/mir-core/skills",
                "plugins/mir-content/skills",
            ],
            "settings_files": [],
            "agents_md": "AGENTS.md",
            "memory_marker": "mir:generated",
            "marker_surfaces": [],
            "mirror_heading": "## Memory (DB-canonical",
        },
    )

    assert [finding.location for finding in findings] == [
        "plugins/mir-content/skills/knowledge"
    ]


def test_r17_mirror_contract_missing_heading(tmp_path):
    """mirror_contract: AGENTS.md missing required memory heading triggers finding."""
    from tools.harness_consistency.rules import agent_surface_contract
    root = tmp_path / "mirror_gap"
    root.mkdir()
    _write_text_r17(root / "CLAUDE.md", "## Memory (DB-canonical -- ADR-50)\nok")
    _write_text_r17(root / "AGENTS.md", "# no memory heading here")
    rule_inputs = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [],
        "agents_md": "AGENTS.md",
        "memory_marker": "mir:generated",
        "marker_surfaces": [],
        "mirror_heading": "## Memory (DB-canonical",
    }
    findings = agent_surface_contract(root, rule_inputs)
    mirror_findings = [
        f
        for f in findings
        if "mirror" in f.message.lower()
        or "AGENTS.md" in f.message
    ]
    assert len(mirror_findings) >= 1, (
        f"Expected mirror_contract finding, got: {findings}"
    )


def test_r17_marker_pairs_missing_on_memory_map(tmp_path):
    """marker_pairs: docs/memory-map.md with 0 markers is a finding."""
    from tools.harness_consistency.rules import agent_surface_contract
    root = tmp_path / "marker_gap"
    root.mkdir()
    _write_text_r17(root / "CLAUDE.md", "")
    _write_text_r17(root / "docs" / "memory-map.md", "# no markers here")
    rule_inputs = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [],
        "agents_md": "AGENTS.md",
        "memory_marker": "mir:generated",
        "marker_surfaces": ["docs/memory-map.md"],
        "mirror_heading": "## Memory (DB-canonical",
    }
    findings = agent_surface_contract(root, rule_inputs)
    marker_findings = [
        f
        for f in findings
        if "marker" in f.message.lower()
        or "memory-map" in f.message
    ]
    assert len(marker_findings) >= 1, (
        f"Expected marker_pairs finding for 0 markers, got: {findings}"
    )


def test_r17_marker_pairs_unbalanced(tmp_path):
    """marker_pairs: unbalanced start/end marker counts trigger finding."""
    from tools.harness_consistency.rules import agent_surface_contract
    root = tmp_path / "marker_unbalanced"
    root.mkdir()
    _write_text_r17(root / "CLAUDE.md", "")
    _write_text_r17(root / "docs" / "memory-map.md", "<!-- mir:generated:start -->\nstuff")
    rule_inputs = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [],
        "agents_md": "AGENTS.md",
        "memory_marker": "mir:generated",
        "marker_surfaces": ["docs/memory-map.md"],
        "mirror_heading": "## Memory (DB-canonical",
    }
    findings = agent_surface_contract(root, rule_inputs)
    marker_findings = [
        f
        for f in findings
        if "marker" in f.message.lower()
        or "memory-map" in f.message
    ]
    assert len(marker_findings) >= 1, (
        f"Expected marker_pairs finding for unbalanced, got: {findings}"
    )


# R17 runner-path tests (review follow-up: FIX 1)

def test_r17_rules_registry_contains_agent_surface_contract():
    from tools.harness_consistency.rules import RULES

    assert "agent_surface_contract" in RULES, (
        "agent_surface_contract not found in RULES — runner cannot dispatch R17"
    )


def _make_r17_violation_repo(tmp_path):
    root = tmp_path / "r17_violation_repo"
    root.mkdir()
    _write_text_r17(root / "CLAUDE.md", "# Harness\n")
    _write_text_r17(
        root / ".claude" / "settings.json",
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "hooks": [
                                {
                                    "command": ".claude/hooks/dead-script.sh",
                                }
                            ]
                        }
                    ]
                }
            }
        ),
    )
    return root


def _make_r17_runner_manifest(repo_root):
    return {
        "repo": {
            "slug": "test-r17-runner",
            "repository_type": "code_app",
            "role": "code_tdd_review_plane",
            "enforcement": {
                "tools_commit_gate": "lint_test",
                "tools_tdd_ledger": "changes_array",
            },
        },
        "rules": [
            {
                "id": "R17",
                "name": "agent_surface_contract",
                "severity": "ERROR",
                "enabled": True,
                "drift_class": 8,
            }
        ],
        "rule_inputs": {
            "agent_surface_contract": {
                "claude_md": "CLAUDE.md",
                "agents_dir": ".claude/agents",
                "skills_dir": ".claude/skills",
                "settings_files": [".claude/settings.json"],
                "agents_md": "AGENTS.md",
                "memory_marker": "mir:generated",
                "marker_surfaces": [],
                "mirror_heading": "## Memory (DB-canonical",
            }
        },
    }


def test_r17_runner_path_surfaces_dead_hook_finding(tmp_path):
    from tools.harness_consistency.runner import run_with_manifest

    repo_root = _make_r17_violation_repo(tmp_path)
    manifest = _make_r17_runner_manifest(repo_root)
    result = run_with_manifest(repo_root, manifest)
    r17_findings = [
        f
        for f in result["findings"]
        if f["rule_id"] == "R17"
    ]

    assert len(r17_findings) >= 1
    assert result["overall"] == "fail"
    assert (
        r17_findings[0]["rule_id"] == "R17"
        and r17_findings[0]["rule_name"] == "agent_surface_contract"
        and "dead-script.sh" in r17_findings[0]["message"]
    )

def test_r17_glob_pattern_citation_not_flagged(tmp_path):
    """cited_paths: glob-pattern citations (containing * or ?) must NOT produce a finding.

    Field case: CLAUDE.md cites `.claude/skills/*/SKILL.md` (a documentation glob
    describing 15 real on-disk files).  No literal path matching that string exists,
    so the old filter incorrectly reported 'does not exist'.
    """
    from tools.harness_consistency.rules import agent_surface_contract

    root = tmp_path / "glob_repo"
    root.mkdir()
    _write_text_r17(
        root / "CLAUDE.md",
        "Skills live at `.claude/skills/*/SKILL.md` and hooks at `.claude/hooks/pre-?.sh`.",
    )
    rule_inputs = {
        "claude_md": "CLAUDE.md",
        "agents_dir": ".claude/agents",
        "skills_dir": ".claude/skills",
        "settings_files": [],
        "agents_md": "AGENTS.md",
        "memory_marker": "mir:generated",
        "marker_surfaces": [],
        "mirror_heading": "## Memory",
    }
    findings = agent_surface_contract(root, rule_inputs)
    cited = [f for f in findings if "cited_paths" in f.message]
    assert cited == [], (
        f"Glob-pattern citations must not produce cited_paths findings; got: {cited}"
    )
