#!/usr/bin/env python3
"""ADR-42 template applied-state verification tool.

ADR completeness skips source-repo ADRs marked with frontmatter
``template_scope: mir-private`` when they are absent from the public template.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REQUIRED_SCHEMAS = [
    "run_state",
    "task_state",
    "tool_event",
    "approval",
    "memory_entry",
    "design_doc",
    "fleet_harness_state",
    "family_config",
    "phase",
    "report_contract",
    "adr",
    "arch",
    "skill",
    "prd",
    "review-rounds",
    "s4_input",
    "tdd",
    "agent_frontmatter",
    "mir_agent_self_health",
]


CHECK_LABELS = {
    "1": "Phase Documents",
    "2": "Schema Completeness",
    "3": "ADR Completeness",
    "4": "Versioning Artifacts",
    "5": "Sanitize",
    "6": "Catalog Drift",
    "7": "Role Policy Parity",
    "8": "Referenced Safeguards",
}

ROLE_POLICY_SNIPPETS = (
    "The opened Claude or Codex CLI acts as `control_plane`; "
    "both own final scope and verification.",
    "`codex_first` / `code_tdd_review_plane` is a delegated-lane preference, "
    "not a direct-work gate.",
    "All detailed path, capability, boundary, and gate values remain canonical "
    "in `.mir/repo-profile.toml`",
)


def _finding(category, severity, detail, remediation):
    return {
        "category": category,
        "severity": severity,
        "detail": detail,
        "remediation": remediation,
    }


def _check_phase_documents(template_path: Path) -> list[dict]:
    findings = []
    phase_dir = template_path / "docs" / "harness-engineering"
    required_markers = ("## 0.5", "Exit Criterion", "Applied State")

    for phase_number in range(13):
        matches = sorted(phase_dir.glob(f"phase-{phase_number}-*.md"))
        if not matches:
            findings.append(
                _finding(
                    "phase",
                    "major",
                    f"Missing phase document for phase-{phase_number}",
                    "Add docs/harness-engineering/phase-{N}-*.md for every phase 0..12.",
                )
            )
            continue

        phase_satisfied = any(
            all(marker in phase_file.read_text(encoding="utf-8", errors="replace")
                for marker in required_markers)
            for phase_file in matches
        )
        if not phase_satisfied:
            findings.append(
                _finding(
                    "phase",
                    "minor",
                    f"phase-{phase_number}: no document carries all applied-state markers",
                    (
                        f"Ensure at least one phase-{phase_number}-*.md "
                        "(e.g. the baseline) carries the ADR-39 applied-state markers."
                    ),
                )
            )

    return findings


def _check_schema_completeness(template_path: Path) -> list[dict]:
    findings = []
    schema_dir = template_path / "docs" / "templates" / "_schema"

    for slug in REQUIRED_SCHEMAS:
        schema_path = schema_dir / f"{slug}.schema.json"
        if not schema_path.exists():
            findings.append(
                _finding(
                    "schema",
                    "major",
                    f"Missing schema: {slug}.schema.json",
                    "Add the missing schema artifact under docs/templates/_schema.",
                )
            )

    return findings


def _adr_number(path: Path):
    match = re.match(r"adr-(\d+)-.*\.md$", path.name)
    if not match:
        return None
    return match.group(1)


def _scan_adr_numbers(decision_dir: Path):
    adr_by_number = {}
    if not decision_dir.exists():
        return adr_by_number

    for adr_path in sorted(decision_dir.iterdir()):
        if not adr_path.is_file():
            continue
        number = _adr_number(adr_path)
        if number is not None:
            adr_by_number[number] = adr_path

    return adr_by_number


def _frontmatter_values(path: Path) -> dict[str, list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    delimiter_indexes = [index for index, line in enumerate(lines) if line.strip() == "---"]
    if len(delimiter_indexes) < 2:
        return {}

    start, end = delimiter_indexes[0], delimiter_indexes[1]
    values: dict[str, list[str]] = {}
    current_key: str | None = None
    for raw_line in lines[start + 1 : end]:
        stripped = raw_line.strip()
        if not stripped:
            continue

        if stripped.startswith("- ") and current_key:
            values.setdefault(current_key, []).append(stripped.removeprefix("- ").strip())
            continue

        if ":" not in stripped:
            current_key = None
            continue

        key, value = stripped.split(":", 1)
        current_key = key.strip()
        values.setdefault(current_key, [])
        value = value.strip()
        if value:
            values[current_key].append(value)
    return values


def _check_adr_completeness(template_path: Path, mir_self_path: Path) -> list[dict]:
    """Check template ADR coverage.

    Missing mir-self ADRs with ``template_scope: mir-private`` frontmatter are
    intentionally private and do not produce findings.
    """
    findings = []
    mir_adrs = _scan_adr_numbers(mir_self_path / "docs" / "decisions")
    template_adrs = _scan_adr_numbers(template_path / "docs" / "decisions")

    for number, mir_adr_path in mir_adrs.items():
        if number not in template_adrs:
            if "mir-private" in _frontmatter_values(mir_adr_path).get("template_scope", []):
                continue
            findings.append(
                _finding(
                    "adr",
                    "minor",
                    mir_adr_path.name,
                    "Port or intentionally document the missing ADR in the template ADR catalog.",
                )
            )

    return findings


def _check_versioning(template_path: Path) -> list[dict]:
    findings = []
    version_path = template_path / "VERSION"
    changelog_path = template_path / "CHANGELOG.md"
    migration_path = template_path / "MIGRATION.md"

    if not version_path.exists():
        findings.append(
            _finding(
                "versioning",
                "major",
                "Missing VERSION",
                "Add a VERSION file at the template repository root.",
            )
        )

    if not changelog_path.exists():
        findings.append(
            _finding(
                "versioning",
                "major",
                "Missing CHANGELOG.md",
                "Add CHANGELOG.md with a '# Changelog' heading and release entries.",
            )
        )
    else:
        content = changelog_path.open("r", encoding="utf-8", errors="replace").read(1024)
        if not content.startswith("# Changelog") or not re.search(r"## \[", content):
            findings.append(
                _finding(
                    "versioning",
                    "major",
                    "CHANGELOG.md is missing required changelog structure",
                    "Start CHANGELOG.md with '# Changelog' and include at least one '## [' entry.",
                )
            )

    if not migration_path.exists():
        findings.append(
            _finding(
                "versioning",
                "minor",
                "Missing MIGRATION.md",
                "Add MIGRATION.md describing template migration guidance.",
            )
        )

    return findings


def _has_hangul(content: str) -> bool:
    return re.search(r"[\uac00-\ud7af\u3130-\u318f\u1100-\u11ff]", content) is not None


_SANITIZE_EXTENSIONS = {
    ".md",
    ".py",
    ".sh",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".txt",
    ".sql",
}
_SANITIZE_EXCLUDED_DIRS = {
    ".venv",
    "site-packages",
    ".git",
    "archive",
    "node_modules",
    "__pycache__",
}

# Files that contain Hangul by design (regex samples, glossaries) and must not
# be flagged as sanitize violations.
_SANITIZE_ALLOWLIST = frozenset({
    "docs/harness-engineering/applications/template-repo/ci.md",
    "docs/harness-engineering/applications/template-repo/sanitize-glossary.md",
})


def _hangul_sample(content: str) -> list[str]:
    return re.findall(r"[\uac00-\ud7af\u3130-\u318f\u1100-\u11ff]", content)[:5]


def _check_sanitize(template_path: Path) -> list[dict]:
    findings = []

    for path in sorted(template_path.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in _SANITIZE_EXTENSIONS:
            continue
        rel_path = path.relative_to(template_path)
        rel_parts = rel_path.parts
        if any(part in _SANITIZE_EXCLUDED_DIRS for part in rel_parts):
            continue
        if rel_path.as_posix() in _SANITIZE_ALLOWLIST:
            continue

        content = path.read_text(encoding="utf-8", errors="replace")
        if _has_hangul(content):
            findings.append(
                _finding(
                    "sanitize",
                    "major",
                    f"{path}: Hangul sample={_hangul_sample(content)}",
                    (
                        "Remove Hangul from public template files or move "
                        "private content to an exempt path."
                    ),
                )
            )

    return findings


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_markdown_contract_text(text: str) -> str:
    text = text.replace("**", "").replace("`", "")
    return " ".join(text.split())


def _check_role_policy_parity(template_path: Path) -> list[dict]:
    findings = []

    claude_path = template_path / "CLAUDE.md"
    agents_path = template_path / "AGENTS.md"
    profile_template_path = template_path / "docs" / "templates" / "repo-profile.template.toml"

    required_files = {
        "runtime_contract": (claude_path, agents_path),
        "profile_template": (profile_template_path,),
    }
    for _category, paths in required_files.items():
        for path in paths:
            if not path.exists():
                findings.append(
                    _finding(
                        "role_policy",
                        "major",
                        f"Missing required role-policy artifact: {path.relative_to(template_path)}",
                        (
                            "Restore the template role-policy surface before claiming "
                            "applied-state pass."
                        ),
                    )
                )
    if findings:
        return findings

    claude_text = _normalize_markdown_contract_text(
        claude_path.read_text(encoding="utf-8", errors="replace")
    )
    agents_text = _normalize_markdown_contract_text(
        agents_path.read_text(encoding="utf-8", errors="replace")
    )
    for snippet in ROLE_POLICY_SNIPPETS:
        normalized = _normalize_markdown_contract_text(snippet)
        if normalized not in claude_text:
            findings.append(
                _finding(
                    "role_policy",
                    "major",
                    f"CLAUDE.md missing role-policy contract snippet: {snippet}",
                    (
                        "Regenerate or repair CLAUDE.md so the public template exposes "
                        "main-agent parity and delegated Codex-first defaults."
                    ),
                )
            )
        if normalized not in agents_text:
            findings.append(
                _finding(
                    "role_policy",
                    "major",
                    f"AGENTS.md missing role-policy contract snippet: {snippet}",
                    (
                        "Regenerate or repair AGENTS.md so the public template mirrors "
                        "the same runtime contract."
                    ),
                )
            )

    profile_template_text = profile_template_path.read_text(encoding="utf-8", errors="replace")
    for required_line in (
        'main_agent_contract = "shared_parity"',
        'delegated_execution_contract = "subagents_codex_first"',
    ):
        if required_line not in profile_template_text:
            findings.append(
                _finding(
                    "role_policy",
                    "major",
                    f"repo-profile template missing contract field: {required_line}",
                    (
                        "Update the public template repo-profile baseline so new "
                        "repositories inherit the parity contract by default."
                    ),
                )
            )

    return findings


_AI_HARNESS_REF_RE = re.compile(r"`(\.ai-harness/[^`]+\.(?:md|yaml))`")


def _check_referenced_safeguards(template_path: Path) -> list[dict]:
    """Check that every .ai-harness/*.{md,yaml} path cited in CLAUDE.md or AGENTS.md exists."""
    findings = []
    referenced: set[str] = set()

    for doc_name in ("CLAUDE.md", "AGENTS.md"):
        doc_path = template_path / doc_name
        if not doc_path.exists():
            continue
        content = doc_path.read_text(encoding="utf-8", errors="replace")
        for match in _AI_HARNESS_REF_RE.finditer(content):
            referenced.add(match.group(1))

    for rel_path in sorted(referenced):
        if not (template_path / rel_path).exists():
            findings.append(
                _finding(
                    "referenced_safeguards",
                    "major",
                    f"Referenced safeguard file missing: {rel_path}",
                    (
                        f"Add {rel_path} to the template repository so all "
                        "CLAUDE.md / AGENTS.md references resolve."
                    ),
                )
            )

    return findings


def _phase_number(phase_key: str):
    match = re.match(r"phase-(\d+)$", phase_key)
    if not match:
        return None
    return int(match.group(1))


def _check_catalog_drift(template_path: Path, mir_self_path: Path) -> list[dict]:
    findings = []
    fleet_state_path = mir_self_path / "config" / "fleet-harness-state.json"
    if not fleet_state_path.exists():
        return findings

    fleet_state = _load_json(fleet_state_path)
    families = fleet_state.get("families", {})
    family_state = families.get("<example-family>", {})
    adoption = family_state.get("adoption", {})

    for phase_key, phase_data in adoption.items():
        status = phase_data.get("status", "")
        if status not in ("opt_in_pending", "adopted"):
            continue

        phase_number = _phase_number(phase_key)
        if phase_number is None:
            continue
        if phase_number > 12:
            continue

        phase_glob = (
            template_path
            / "docs"
            / "harness-engineering"
            / f"phase-{phase_number}-*.md"
        )
        if not list(phase_glob.parent.glob(phase_glob.name)):
            findings.append(
                _finding(
                    "catalog",
                    "major",
                    f"{phase_key}: catalog={status}, physical=not_adopted",
                    (
                        "Reconcile fleet-harness-state.json or add the missing "
                        "physical phase document."
                    ),
                )
            )

    return findings


def _git_short_head(template_path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=template_path,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"

    commit = result.stdout.strip()
    if result.returncode != 0 or not commit:
        return "unknown"
    return commit


def _read_version(template_path: Path):
    version_path = template_path / "VERSION"
    if not version_path.exists():
        return None
    return version_path.read_text(encoding="utf-8", errors="replace").strip() or None


def _overall(findings):
    """Compute overall verdict per ADR-42 Decision Outputs table.

    Returns one of: 'fail', 'partial', 'pass'.
    - Major 1+          -> 'fail'
    - Major 0, Minor 1+ -> 'partial'
    - Major 0, Minor 0  -> 'pass'
    """
    if any(finding["severity"] == "major" for finding in findings):
        return "fail"
    if any(finding["severity"] == "minor" for finding in findings):
        return "partial"
    return "pass"


def _format_console_report(
    template_path,
    template_commit,
    template_version,
    checks,
    findings,
    overall,
):
    lines = []
    lines.append("=== Template Applied-State Verification ===")
    lines.append(
        f"template: {template_path} "
        f"(commit {template_commit}, version {template_version or 'missing'})"
    )
    lines.append(
        "baseline: ADR-39 "
        "(13 phase + 19 schema + ADR catalog + versioning + sanitize + role-policy parity"
        " + referenced safeguards)"
    )
    lines.append("")

    for check_number in ("1", "2", "3", "4", "5", "6", "7", "8"):
        lines.append(f"CHECK {check_number}/8 -- {CHECK_LABELS[check_number]}")
        check_findings = checks[check_number]["findings"]
        if check_findings:
            for finding in check_findings:
                lines.append(f'  x {finding["detail"]}')
        else:
            lines.append("  ok no findings")

    major_n = sum(1 for finding in findings if finding["severity"] == "major")
    minor_n = sum(1 for finding in findings if finding["severity"] == "minor")

    lines.append("")
    lines.append("=== Summary ===")
    lines.append(f"  Major: {major_n}")
    lines.append(f"  Minor: {minor_n}")
    lines.append(f"  Overall: {overall.upper()}")
    lines.append("  Recommendation: see findings above")
    return "\n".join(lines)


def _atomic_write_json(path, data):
    """Atomic write via tempfile + os.replace. No partial-write risk."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f'.{path.name}.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n')
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _auto_reconcile(mir_self_path, findings):
    catalog_findings = [
        finding for finding in findings if finding.get("category") == "catalog"
    ]
    if not catalog_findings:
        return

    fleet_state_path = Path(mir_self_path) / "config" / "fleet-harness-state.json"
    if not fleet_state_path.exists():
        return

    fleet_state = _load_json(fleet_state_path)
    adoption = (
        fleet_state
        .get("families", {})
        .get("<example-family>", {})
        .get("adoption", {})
    )

    changed = False
    for finding in catalog_findings:
        phase_key = finding.get("detail", "").split(":", 1)[0]
        phase_data = adoption.get(phase_key)
        if isinstance(phase_data, dict):
            phase_data["status"] = "not_adopted"
            changed = True

    if changed:
        _atomic_write_json(fleet_state_path, fleet_state)


def run_verification(
    template_path,
    mir_self_path,
    output="console",
    auto_reconcile=False,
):
    template_path = Path(template_path)
    mir_self_path = Path(mir_self_path)

    checks = {
        "1": {"findings": _check_phase_documents(template_path)},
        "2": {"findings": _check_schema_completeness(template_path)},
        "3": {"findings": _check_adr_completeness(template_path, mir_self_path)},
        "4": {"findings": _check_versioning(template_path)},
        "5": {"findings": _check_sanitize(template_path)},
        "6": {"findings": _check_catalog_drift(template_path, mir_self_path)},
        "7": {"findings": _check_role_policy_parity(template_path)},
        "8": {"findings": _check_referenced_safeguards(template_path)},
    }

    findings = []
    for check_number in ("1", "2", "3", "4", "5", "6", "7", "8"):
        findings.extend(checks[check_number]["findings"])

    template_commit = _git_short_head(template_path)
    template_version = _read_version(template_path)
    overall = _overall(findings)

    result = {
        "overall": overall,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),  # noqa: UP017
        "template_commit": template_commit,
        "template_version": template_version,
        "checks": checks,
        "findings": findings,
    }

    if auto_reconcile and overall != "pass":
        _auto_reconcile(mir_self_path, findings)

    if output == "json":
        return result

    return _format_console_report(
        template_path,
        template_commit,
        template_version,
        checks,
        findings,
        overall,
    )


def _serialize_output(result):
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, sort_keys=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Verify ADR-42 template applied-state completeness."
    )
    parser.add_argument(
        "--template",
        "--template-repo",
        dest="template_repo",
        default=Path(__file__).resolve().parent.parent,
        help="Path to the template repository.",
    )
    parser.add_argument(
        "--mir-self",
        "--mir-self-repo",
        dest="mir_self_repo",
        default=Path(__file__).resolve().parent.parent,
        help="Path to the your-harness self repository.",
    )
    parser.add_argument(
        "--baseline-adr",
        help="Informational ADR path; not used by checks.",
    )
    parser.add_argument(
        "--format",
        "--output",
        dest="output",
        choices=("console", "json", "markdown"),
        default="console",
        help="Output format.",
    )
    parser.add_argument(
        "--report",
        help="Write output to this path instead of stdout.",
    )
    parser.add_argument(
        "--auto-reconcile",
        action="store_true",
        help="Demote catalog drift phases to not_adopted.",
    )

    args = parser.parse_args(argv)
    template_path = Path(args.template_repo)
    mir_self_path = Path(args.mir_self_repo)

    if not template_path.exists():
        message = f"Template repo missing: {template_path}"
        print(message, file=sys.stderr)
        sys.exit(2)

    result = run_verification(
        template_path,
        mir_self_path,
        output=args.output,
        auto_reconcile=args.auto_reconcile,
    )
    rendered = _serialize_output(result)

    if args.report:
        Path(args.report).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    overall = result["overall"] if isinstance(result, dict) else None
    if overall is None:
        json_result = run_verification(
            template_path,
            mir_self_path,
            output="json",
            auto_reconcile=False,
        )
        overall = json_result["overall"]

    if overall == "fail":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
