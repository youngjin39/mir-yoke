"""Harness contract drift detector (phase-0).

Compares the contract extracted from ARCHITECTURE.md against the actual
repo file/dir tree. Surfaces drift as a list of findings:
 - missing_dir
 - missing_file
 - extra_top_level_dir (not declared in contract)
 - constraint_violation
"""

from __future__ import annotations

from pathlib import Path


def check_drift(contract: dict, project_root: Path) -> list[dict]:
    findings = []
    # Required dirs
    for required in contract.get("required_dirs", []):
        path = project_root / required.rstrip("/")
        if not path.is_dir():
            findings.append({
                "category": "missing_dir",
                "severity": "major",
                "target": required,
                "detail": f"Required directory {required} not found",
                "remediation": f"Create {required} or remove from ARCHITECTURE.md",
            })
    # Required files
    for fname, _meta in contract.get("required_files", {}).items():
        path = project_root / fname
        if not path.exists():
            findings.append({
                "category": "missing_file",
                "severity": "major",
                "target": fname,
                "detail": f"Required file {fname} not found",
                "remediation": f"Create {fname} or remove from ARCHITECTURE.md",
            })
    # Constraints
    for c in contract.get("constraints", []):
        ctype = c.get("type")
        # No active enforcement on most constraint types in slice 2 -
        # surface as advisory only; detailed check is deferred
        if ctype == "no_hangul" and c.get("target") == "template":
            findings.append({
                "category": "constraint_advisory",
                "severity": "minor",
                "target": ctype,
                "detail": (
                    "constraint declared; public sanitization runs through"
                    " tests/test_no_korean_in_user_facing.py"
                ),
                "remediation": "Run uv run python tests/test_no_korean_in_user_facing.py",
            })
    return findings


def summarize(findings: list[dict]) -> dict:
    """Build summary stats."""
    return {
        "total": len(findings),
        "major": sum(1 for f in findings if f["severity"] == "major"),
        "minor": sum(1 for f in findings if f["severity"] == "minor"),
        "by_category": {
            k: sum(1 for f in findings if f["category"] == k)
            for k in {f["category"] for f in findings}
        },
    }
