#!/usr/bin/env python3
"""Verifier for config/repo-agent-management.json.

Verifier for the Claude+Codex Harness Template.
Runs the general-purpose checks (schema, catalog drift, template pack cross-ref,
R10 scope_patterns, R11 dispatch log, R12 repos-dir integrity).

Fleet-specific checks (registry alignment, profile source cross-ref, fleet override
enforcement) are skipped because the public template starts with an empty
repositories_dir and no per-family entries.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.catalog_loader import load_catalog  # noqa: E402

MANIFEST_PATH = ROOT / "config" / "repo-agent-management.json"
SCHEMA_PATH = ROOT / "config" / "repo-agent-management.schema.json"
DOMAIN_NAMES = [
    "central_ownership_contract",
    "repository_overlay",
    "generation_verification_pipeline",
    "operating_contract",
    "harness_structure",
    "harness_format",
    "agent_management",
]


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_schema(manifest: dict) -> None:
    schema = _load_json(SCHEMA_PATH)
    jsonschema.Draft202012Validator(schema).validate(manifest)


def _validate_template_contract(manifest: dict) -> None:
    domains = set(manifest["management_domains"])
    expected = set(DOMAIN_NAMES)
    if domains != expected:
        raise AssertionError(
            f"management_domains mismatch: {sorted(domains)} != {sorted(expected)}"
        )

    templates = manifest["templates"]
    for template_id, template in templates.items():
        tracked = set(template["tracked_paths"])
        if tracked != expected:
            raise AssertionError(
                f"{template_id}: tracked_paths keys mismatch:"
                f" {sorted(tracked)} != {sorted(expected)}"
            )

    for entry in manifest.get("repositories", []):
        template_id = entry["management_template_id"]
        if template_id not in templates:
            raise AssertionError(f"{entry['slug']}: unknown template {template_id!r}")


def _validate_catalog_drift(manifest: dict) -> tuple[list[str], list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []
    infos: list[str] = []

    catalog_agents = manifest["catalog"]["agents"]
    catalog_skills = manifest["catalog"]["skills"]

    for slug, meta in catalog_agents.items():
        expected_path = meta["source_path"]
        if meta["status"] == "archived":
            continue
        elif meta["status"] == "external":
            if expected_path != "external":
                errors.append(f"AGENT {slug}: external status but source_path != external")
            continue
        elif meta["status"] == "proposed":
            path = ROOT / expected_path
            if not path.exists():
                infos.append(f"AGENT {slug}: proposed, file pending")
            else:
                infos.append(f"AGENT {slug}: proposed, file present - review for active flip")
            continue
        elif meta["status"] == "active":
            path = ROOT / expected_path
            if not path.exists():
                errors.append(f"AGENT {slug}: status=active but file missing: {expected_path}")
        else:
            warns.append(
                f"AGENT {slug}: unknown status {meta['status']!r}"
                " — schema/verifier drift, update verifier"
            )

    for actual_file in (ROOT / ".claude/agents").glob("*.md"):
        slug = actual_file.stem
        if slug == "README":
            continue
        if slug not in catalog_agents:
            warns.append(
                f"AGENT {slug}: directory file present but no catalog entry - refresh needed"
            )

    for slug, meta in catalog_skills.items():
        src = meta["source_path"]
        if meta["status"] == "archived":
            continue
        elif meta["status"] == "external":
            if src != "external":
                errors.append(f"SKILL {slug}: external status but source_path != external")
            continue
        elif meta["status"] == "proposed":
            path = ROOT / src
            if not path.is_dir():
                infos.append(f"SKILL {slug}: proposed, dir pending")
            else:
                infos.append(f"SKILL {slug}: proposed, dir present - review for active flip")
            continue
        elif meta["status"] == "active":
            path = ROOT / src
            if not path.is_dir():
                errors.append(f"SKILL {slug}: active but dir missing: {src}")
            elif not (path / "SKILL.md").is_file():
                errors.append(f"SKILL {slug}: active but SKILL.md missing: {src}")
        elif meta["status"] == "consolidated":
            continue
        else:
            warns.append(
                f"SKILL {slug}: unknown status {meta['status']!r}"
                " — schema/verifier drift, update verifier"
            )

    skill_roots = sorted(
        {
            (ROOT / meta["source_path"]).parent
            for meta in catalog_skills.values()
            if meta["status"] in {"active", "proposed"} and meta["source_path"] != "external"
        }
    )
    for skills_dir in skill_roots:
        if not skills_dir.is_dir():
            continue
        for actual_dir in skills_dir.iterdir():
            if actual_dir.is_dir() and actual_dir.name not in catalog_skills:
                warns.append(
                    f"SKILL {actual_dir.name}: directory present but no catalog entry"
                    " - refresh needed"
                )

    return (errors, warns, infos)


def _validate_template_pack_refs(manifest: dict) -> list[str]:
    """Each template's default_agent_pack refs must resolve in catalog.agents.
    Each template's default_skill_pack refs must resolve in catalog.skills.
    """
    errors: list[str] = []
    catalog_agents = manifest.get("catalog", {}).get("agents", {})
    catalog_skills = manifest.get("catalog", {}).get("skills", {})

    for key, template in manifest.get("templates", {}).items():
        agent_pack = template.get("default_agent_pack", {})
        for field in ("orchestrator", "executor"):
            slug = agent_pack.get(field)
            if slug and slug not in catalog_agents:
                errors.append(
                    f"template {key}.default_agent_pack.{field} ref {slug!r} not in catalog.agents"
                )
        for field in ("reviewers", "specialists"):
            for slug in agent_pack.get(field, []):
                if slug not in catalog_agents:
                    errors.append(
                        f"template {key}.default_agent_pack.{field} ref {slug!r}"
                        " not in catalog.agents"
                    )

        skill_pack = template.get("default_skill_pack", {})
        for bucket in ("core", "code", "domain"):
            for slug in skill_pack.get(bucket, []):
                if slug not in catalog_skills:
                    errors.append(
                        f"template {key}.default_skill_pack.{bucket} ref {slug!r}"
                        " not in catalog.skills"
                    )

    return errors


def _check_active_specialist_scope_patterns_declared(manifest: dict) -> list[str]:
    """R10: Every catalog.agents[slug] with role=specialist AND status=active
    should declare scope_patterns (advisory WARN if absent).
    """
    warns: list[str] = []
    catalog_agents = manifest.get("catalog", {}).get("agents", {})

    for slug, meta in catalog_agents.items():
        if meta.get("role") != "specialist":
            continue
        if meta.get("status") != "active":
            continue
        if "scope_patterns" not in meta:
            warns.append(
                f"specialist {slug!r} is status=active but has no scope_patterns declared"
                " — falls back to no-filter ['**/*']."
            )

    return warns


def _check_codex_backend_dispatch_log(manifest: dict) -> tuple[list[str], list[str], list[str]]:
    """R11: Audit tasks/log/dispatch-log.jsonl for codex-backend routing compliance."""
    errors: list[str] = []
    warns: list[str] = []
    infos: list[str] = []

    dispatch_log_path = ROOT / "tasks" / "log" / "dispatch-log.jsonl"

    if not dispatch_log_path.exists():
        infos.append("dispatch log absent — codex-backend routing audit skipped")
        return errors, warns, infos

    catalog_agents = manifest.get("catalog", {}).get("agents", {})
    codex_backend_slugs = {
        slug for slug, meta in catalog_agents.items() if meta.get("execution_backend") == "codex"
    }

    total = 0
    compliant = 0
    non_compliant = 0

    for lineno, line in enumerate(dispatch_log_path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            warns.append(f"dispatch-log.jsonl line {lineno}: unparseable JSON — skipped")
            continue

        agent_slug = entry.get("agent_slug", "")
        if agent_slug not in codex_backend_slugs:
            continue

        total += 1
        routed_via = entry.get("routed_via", "")
        if routed_via == "codex_cli":
            compliant += 1
        else:
            non_compliant += 1
            warns.append(
                f"dispatch-log.jsonl: agent_slug={agent_slug!r}"
                f" routed_via={routed_via!r}"
                " (expected 'codex_cli')"
            )

    infos.append(
        f"OK: codex-backend dispatch log audit: {total} entries,"
        f" {compliant} compliant, {non_compliant} non-compliant"
    )
    return errors, warns, infos


def _check_repositories_dir_integrity(_manifest_unused: dict) -> list[str]:
    """R12: repositories_dir integrity check.

    - If repositories_dir is set, root repositories must be absent — no dual source.
    - If config/repos/ exists, every .json file slug must match its filename.
    """
    errors: list[str] = []
    try:
        raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        errors.append(f"R12: cannot read root manifest: {exc}")
        return errors
    repos_dir_val = raw.get("repositories_dir")
    if repos_dir_val is not None:
        root_repos = raw.get("repositories")
        if root_repos:
            errors.append(
                "R12: repositories_dir is set but root repositories[] is also present"
                " — dual source not allowed"
            )
    repos_dir_path = ROOT / "config" / "repos"
    if repos_dir_path.is_dir():
        for repo_file in sorted(repos_dir_path.glob("*.json")):
            if repo_file.name.startswith("_"):
                continue
            try:
                entry = json.loads(repo_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"R12: {repo_file.name}: JSON parse error: {exc}")
                continue
            slug = entry.get("slug")
            expected_name = f"{slug}.json"
            if repo_file.name != expected_name:
                errors.append(
                    f"R12: slug-filename mismatch: file={repo_file.name!r}"
                    f" but slug={slug!r} (expected {expected_name!r})"
                )
    return errors


def _print_findings(errors: list[str], warns: list[str], infos: list[str]) -> None:
    for info in infos:
        print(f"INFO: {info}")
    for warn in warns:
        print(f"WARN: {warn}")
    for error in errors:
        print(f"ERROR: {error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify config/repo-agent-management.json")
    parser.add_argument(
        "--check-drift",
        action="store_true",
        help="Run only the catalog drift check.",
    )
    args, _ = parser.parse_known_args(argv)

    manifest = load_catalog(ROOT)

    if args.check_drift:
        if "catalog" not in manifest:
            return 0
        errors, warns, infos = _validate_catalog_drift(manifest)
        _print_findings(errors, warns, infos)
        if errors:
            print("DRIFT: errors detected")
            return 1
        print("OK: catalog drift check passed")
        return 0

    # 1. Schema validation
    _validate_schema(manifest)
    print("OK: repo-agent-management manifest validates against its schema")

    # 2. Template/domain wiring
    _validate_template_contract(manifest)
    print("OK: template/domain wiring is complete")

    # 3. Catalog drift
    if "catalog" in manifest:
        errors, warns, infos = _validate_catalog_drift(manifest)
        _print_findings(errors, warns, infos)
        if errors:
            print("DRIFT: errors detected")
            return 1
        print("OK: catalog drift check passed")

        # Template pack cross-ref
        tp_errors = _validate_template_pack_refs(manifest)
        for error in tp_errors:
            print(f"ERROR: {error}")
        if tp_errors:
            print("TEMPLATE-PACK: errors detected")
            return 1
        print("OK: template pack cross-ref check passed")

        # R10: scope_patterns declared
        r10_warns = _check_active_specialist_scope_patterns_declared(manifest)
        for warn in r10_warns:
            print(f"WARN: {warn}")
        print("OK: active-specialist scope_patterns declaration check passed")

        # R11: dispatch log audit
        r11_errors, r11_warns, r11_infos = _check_codex_backend_dispatch_log(manifest)
        for info in r11_infos:
            print(f"INFO: {info}")
        for warn in r11_warns:
            print(f"WARN: {warn}")
        for error in r11_errors:
            print(f"ERROR: {error}")
        if r11_errors:
            print("DISPATCH-LOG: errors detected")
            return 1

    # R12: repositories_dir integrity
    r12_errors = _check_repositories_dir_integrity(manifest)
    for error in r12_errors:
        print(f"ERROR: {error}")
    if r12_errors:
        print("REPOS-DIR: integrity errors detected")
        return 1
    print("OK: repositories_dir integrity check passed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
