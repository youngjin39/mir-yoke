from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from tools.harness_consistency.runner import run_with_manifest

_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_MANIFEST = _SOURCE_ROOT / "config" / "harness-consistency.json"

_DIRECT_STATIC_INPUTS = (
    "adr_status_enum",
    "settings_dual_fire_dedup",
    "single_family_source",
    "catalog_loader_usage",
    "adr_supersession_graph",
    "context_path_references",
    "architecture_contract",
    "generated_marker_rerender",
)
_REMOVED_SYMBOL_KEYS = ("scan_dirs", "file_globs", "allowed_path_substrings")
_HOOK_FILE_REACHABILITY_KEYS = (
    "hooks_dir",
    "file_globs",
    "settings_files",
    "archive_exclude",
)
_ARCHIVED_SOURCE_KEYS = (
    "hook_archive_dir",
    "settings_files",
    "phase_doc_globs",
    "live_claim_keywords",
    "exempt_token",
)
_HOOK_TIER_KEYS = ("hooks_dir", "marker_prefix")
_HOOK_TIER_RE = re.compile(r"\b_MIR_HOOK_TIER\w*\s*=\s*(['\"])(.*?)\1")
_GREEN_NOTE = (
    " In --green mode, ERROR rules listed in disabled_rules were auto-disabled "
    "because they ERROR on this repo and should be re-enabled after the family "
    "adds the prerequisite or tunes the input."
)


def _load_source_manifest() -> dict:
    return json.loads(_SOURCE_MANIFEST.read_text(encoding="utf-8"))


def _copy_selected(source: dict, keys: tuple[str, ...]) -> dict:
    return {key: copy.deepcopy(source[key]) for key in keys}


def _load_profile(profile_path: Path | None) -> dict:
    if profile_path is None:
        return {}
    return json.loads(profile_path.read_text(encoding="utf-8"))


def _repo_slug(repo_root: Path, profile: dict) -> str:
    slug = profile.get("slug")
    if slug:
        return str(slug)
    return repo_root.name or repo_root.resolve().name


def _build_repo_section(repo_root: Path, profile: dict) -> dict:
    repository_type = str(profile.get("repository_type", "unknown"))
    fleet_manager = (repo_root / "config" / "repo-agent-management.json").exists()
    return {
        "slug": _repo_slug(repo_root, profile),
        "repository_type": repository_type,
        "role": (
            "control_plane"
            if repository_type == "meta_harness"
            else "code_tdd_review_plane"
        ),
        "fleet_manager": fleet_manager,
        "enforcement": {
            "tools_commit_gate": "deferred" if fleet_manager else "lint_test",
            "tools_tdd_ledger": "keyed_composite" if fleet_manager else "changes_array",
        },
    }


def _introspect_expected_tiers(repo_root: Path) -> dict[str, str]:
    hooks_root = repo_root / ".claude" / "hooks"
    if not hooks_root.exists():
        return {}

    expected_tiers: dict[str, str] = {}
    for file_glob in ("*.sh", "*.py"):
        for path in sorted(hooks_root.glob(file_glob)):
            if not path.is_file():
                continue

            for line in path.read_text(encoding="utf-8").splitlines():
                if line.lstrip().startswith("#"):
                    continue
                match = _HOOK_TIER_RE.search(line)
                if match is None:
                    continue
                expected_tiers[path.name] = match.group(2)
                break
    return expected_tiers


def _introspect_archived_hook_names(repo_root: Path) -> list[str]:
    archive_root = repo_root / ".claude" / "hooks" / "archive"
    if not archive_root.exists():
        return []

    hook_names = {
        path.stem
        for path in archive_root.iterdir()
        if path.is_file() and path.suffix in {".sh", ".py"}
    }
    return sorted(hook_names)


def _localize_generated_marker_rerender(
    rule_inputs: dict,
    *,
    source_slug: str,
    target_slug: str,
) -> None:
    for surface in rule_inputs["generated_marker_rerender"]["surfaces"]:
        render_args = surface["render_args"]
        for index, arg in enumerate(render_args[:-1]):
            if arg == "--family" and render_args[index + 1] == source_slug:
                render_args[index + 1] = target_slug


def _build_rule_inputs(
    repo_root: Path,
    source_inputs: dict,
    *,
    source_slug: str,
    target_slug: str,
) -> dict:
    rule_inputs = {
        name: copy.deepcopy(source_inputs[name]) for name in _DIRECT_STATIC_INPUTS
    }
    if "template_parity" in source_inputs:
        tp = copy.deepcopy(source_inputs["template_parity"])
        # B2 (ADR-54 §2 D2): decide template_repo per target:
        # - template repo itself -> "." (self-referential, no abs path)
        # - every other target  -> keep the source absolute path verbatim
        #   so checker resolves against the real template, not the family root.
        # Never inherit the source repo's exclude_paths for non-source targets.
        _template_slug = "mir-yoke"
        if target_slug == _template_slug:
            tp["template_repo"] = "."
        else:
            # Keep source absolute path (already set by the source manifest)
            pass  # tp["template_repo"] already present from deepcopy
        # Remove source-specific exclude_paths for non-source targets
        _source_is_mir = source_slug == "mir-harness"
        _target_is_mir = target_slug == "mir-harness"
        if _source_is_mir and not _target_is_mir:
            tp.pop("exclude_paths", None)
        rule_inputs["template_parity"] = tp
    rule_inputs["removed_symbol_references"] = _copy_selected(
        source_inputs["removed_symbol_references"],
        _REMOVED_SYMBOL_KEYS,
    )
    rule_inputs["removed_symbol_references"]["retired_symbols"] = []

    rule_inputs["hook_file_reachability"] = _copy_selected(
        source_inputs["hook_file_reachability"],
        _HOOK_FILE_REACHABILITY_KEYS,
    )
    rule_inputs["hook_file_reachability"]["manual_trigger_allowlist"] = []

    rule_inputs["wired_gate_liveness"] = {"gates": []}

    rule_inputs["archived_source_phase_doc"] = _copy_selected(
        source_inputs["archived_source_phase_doc"],
        _ARCHIVED_SOURCE_KEYS,
    )
    rule_inputs["archived_source_phase_doc"][
        "archived_hook_names"
    ] = _introspect_archived_hook_names(repo_root)

    rule_inputs["code_schema_constraint_agreement"] = {"pairs": []}
    rule_inputs["adr_artifact_present"] = {"artifact_map": {}}

    if "agent_surface_contract" in source_inputs:
        rule_inputs["agent_surface_contract"] = copy.deepcopy(
            source_inputs["agent_surface_contract"]
        )

    rule_inputs["hook_tier_declaration"] = _copy_selected(
        source_inputs["hook_tier_declaration"],
        _HOOK_TIER_KEYS,
    )
    rule_inputs["hook_tier_declaration"][
        "expected_tiers"
    ] = _introspect_expected_tiers(repo_root)
    _localize_generated_marker_rerender(
        rule_inputs,
        source_slug=source_slug,
        target_slug=target_slug,
    )
    return rule_inputs


def _generated_note(repo_slug: str) -> dict:
    return {
        "by": "tools.harness_consistency generate",
        "repo_slug": repo_slug,
        "note": (
            "Irreducible rule_inputs (retired_symbols, gate_liveness, code_schema "
            "pairs, artifact_map, manual_trigger_allowlist) are empty and must be "
            "hand-tuned per family; derivable sections were introspected. Run "
            "`python -m tools.harness_consistency run` and tune until green."
        ),
    }


def _rule_id_sort_key(rule_id: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"([A-Za-z]+)(\d+)", rule_id)
    if match is None:
        return (rule_id, -1, rule_id)
    return (match.group(1), int(match.group(2)), "")


def _error_finding_counts(result: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in result["findings"]:
        if finding["severity"] != "ERROR":
            continue
        rule_id = finding["rule_id"]
        counts[rule_id] = counts.get(rule_id, 0) + 1
    return counts


def _apply_green(repo_root: Path, manifest: dict) -> None:
    result = run_with_manifest(repo_root, manifest)
    error_counts = _error_finding_counts(result)
    disabled_rules: list[dict] = []

    for rule in manifest["rules"]:
        rule_id = rule["id"]
        if rule["severity"] != "ERROR" or rule_id not in error_counts:
            continue
        rule["enabled"] = False
        disabled_rules.append(
            {
                "rule_id": rule_id,
                "rule_name": rule["name"],
                "error_findings": error_counts[rule_id],
            }
        )

    disabled_rules.sort(key=lambda item: _rule_id_sort_key(item["rule_id"]))
    manifest["_generated"]["disabled_rules"] = disabled_rules
    manifest["_generated"]["note"] += _GREEN_NOTE

    rerun_result = run_with_manifest(repo_root, manifest)
    if rerun_result["overall"] != "pass":
        raise RuntimeError(
            "green manifest still fails after disabling ERROR rules: "
            f"{rerun_result['summary']}"
        )


def build_manifest(
    repo_root: Path,
    profile_path: Path | None,
    *,
    green: bool = False,
) -> dict:
    source_manifest = _load_source_manifest()
    profile = _load_profile(profile_path)
    repo = _build_repo_section(repo_root, profile)
    manifest = {
        "$schema": "./harness-consistency.schema.json",
        "version": 1,
        "_generated": _generated_note(repo["slug"]),
        "repo": repo,
        "rules": copy.deepcopy(source_manifest["rules"]),
        "rule_inputs": _build_rule_inputs(
            repo_root,
            source_manifest["rule_inputs"],
            source_slug=str(source_manifest["repo"]["slug"]),
            target_slug=str(repo["slug"]),
        ),
    }
    if green:
        _apply_green(repo_root, manifest)
    return manifest
