"""Specialist agent deployment — host repo → family repository.

ADR-16 P16-A.

Public API
----------
compute_normalized_sha256(path) -> str
get_mir_root() -> Path
get_mir_head_commit() -> str
is_mir_dirty(slug) -> bool
load_ledger(family_root) -> dict
write_ledger(family_root, ledger) -> None
classify_drift(ledger_entry, mir_source_path, deployed_path) -> str
refresh_specialists(family_root, slugs, *, apply=False, dry_run=True) -> dict
SpecialistDeployError(Exception)
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

from tools.catalog_loader import load_catalog

LEDGER_VERSION = 1
LEDGER_RELATIVE_PATH = ".mir/specialists.json"

# Canonical 7 specialist slugs (ADR-15 §S3)
CANONICAL_SPECIALIST_SLUGS: list[str] = [
    "cwe-auditor",
    "dep-auditor",
    "ui-reviewer",
    "pipeline-validator",
    "ontology-validator",
    "runtime-contract-reviewer",
    "template-sync-validator",
]

# Universal agent slugs (ADR-09 §S4) that are deployed to ALL families, not just Mir.
UNIVERSAL_SLUGS: list[str] = [
    "main-orchestrator",
    "executor-agent",
    "codex-final-reviewer",
    "quality-agent",
]


class SpecialistDeployError(Exception):
    """Raised when specialist deployment cannot proceed."""


def compute_normalized_sha256(path: Path) -> str:
    """Return sha256 of normalized UTF-8 text (LF endings, no BOM).

    Normalization:
    - Strip leading UTF-8 BOM (\xef\xbb\xbf / '\ufeff').
    - Normalize CRLF and bare CR to LF.
    - Re-encode as UTF-8 for hashing.
    """
    text = path.read_text(encoding="utf-8")
    # Strip leading BOM
    text = text.lstrip("\ufeff")
    # Normalize line endings: CRLF then bare CR
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_mir_root() -> Path:
    """Return the host repo root (where this harness is installed).

    Resolved as Path(__file__).resolve().parents[2]:
      __file__ = <root>/tools/profile_compiler/specialist_deploy.py
      .parents[0] = <root>/tools/profile_compiler
      .parents[1] = <root>/tools
      .parents[2] = <root>
    """
    return Path(__file__).resolve().parents[2]


def get_mir_head_commit() -> str:
    """Return the current HEAD commit SHA of the Mir repo."""
    mir_root = get_mir_root()
    result = subprocess.run(
        ["git", "-C", str(mir_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def is_mir_dirty(slug: str) -> bool:
    """Return True if the specialist .md file has uncommitted changes in Mir."""
    mir_root = get_mir_root()
    rel_path = f".claude/agents/{slug}.md"
    result = subprocess.run(
        ["git", "-C", str(mir_root), "diff", "--quiet", rel_path],
        capture_output=True,
    )
    # exit 0 = clean, exit 1 = dirty
    return result.returncode != 0


def load_ledger(family_root: Path) -> dict:
    """Load .mir/specialists.json from family_root; return empty schema if missing."""
    ledger_path = family_root / LEDGER_RELATIVE_PATH
    if not ledger_path.exists():
        return {"version": LEDGER_VERSION, "specialists": {}}
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    return data


def write_ledger(family_root: Path, ledger: dict) -> None:
    """Atomically write .mir/specialists.json under family_root."""
    ledger_path = family_root / LEDGER_RELATIVE_PATH
    content = json.dumps(ledger, indent=2, ensure_ascii=False) + "\n"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{ledger_path.name}.",
        suffix=".tmp",
        dir=ledger_path.parent,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_name, str(ledger_path))
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def classify_drift(
    ledger_entry: dict | None,
    mir_source_path: Path,
    deployed_path: Path,
) -> str:
    """Return drift status string.

    Returns one of: "new" | "in_sync" | "family_modified" | "mir_updated" | "both_diverged"

    Algorithm:
    - No ledger entry: "new".
    - Compute current sha256 of both mir_source_path and deployed_path (if deployed exists).
    - Compare against ledger recorded source_sha256 / deployed_sha256.
    """
    if ledger_entry is None:
        return "new"

    recorded_source_sha = ledger_entry.get("source_sha256", "")
    recorded_deployed_sha = ledger_entry.get("deployed_sha256", "")

    current_source_sha = compute_normalized_sha256(mir_source_path) if mir_source_path.exists() else ""
    current_deployed_sha = compute_normalized_sha256(deployed_path) if deployed_path.exists() else ""

    source_changed = current_source_sha != recorded_source_sha
    deployed_changed = current_deployed_sha != recorded_deployed_sha

    if not source_changed and not deployed_changed:
        return "in_sync"
    if not source_changed and deployed_changed:
        return "family_modified"
    if source_changed and not deployed_changed:
        return "mir_updated"
    # both changed
    return "both_diverged"


def print_three_way_diff(
    slug: str,
    mir_root: Path,
    family_root: Path,
    ledger_entry: dict | None,
) -> None:
    """Print three-way diff for a slug to stdout.

    Side A: Mir HEAD content (git show HEAD:.claude/agents/<slug>.md).
    Side B: family-local current content.
    Side C: ledger-baseline content (git show <source_commit>:.claude/agents/<slug>.md).
    """
    rel = f".claude/agents/{slug}.md"
    family_path = family_root / rel

    # Side A: Mir HEAD
    result_a = subprocess.run(
        ["git", "-C", str(mir_root), "show", f"HEAD:{rel}"],
        capture_output=True,
        text=True,
    )
    if result_a.returncode != 0:
        mir_lines: list[str] = []
        mir_label = f"<unreachable: Mir HEAD:{rel}>"
    else:
        mir_lines = result_a.stdout.splitlines(keepends=True)
        mir_label = f"Mir HEAD:{rel}"

    # Side B: family-local current
    if family_path.exists():
        family_lines = family_path.read_text(encoding="utf-8").splitlines(keepends=True)
        family_label = str(family_path)
    else:
        family_lines = []
        family_label = f"<not present: {family_path}>"

    # Side C: ledger-baseline
    source_commit = (ledger_entry or {}).get("source_commit", "")
    if source_commit:
        result_c = subprocess.run(
            ["git", "-C", str(mir_root), "show", f"{source_commit}:{rel}"],
            capture_output=True,
            text=True,
        )
        if result_c.returncode != 0:
            baseline_lines: list[str] = []
            baseline_label = f"<unreachable: source_commit={source_commit}>"
        else:
            baseline_lines = result_c.stdout.splitlines(keepends=True)
            baseline_label = f"ledger-baseline:{source_commit[:8]}:{rel}"
    else:
        baseline_lines = []
        baseline_label = "<no ledger entry>"

    print("=== Mir HEAD vs family-local ===")
    diff_ab = list(difflib.unified_diff(
        mir_lines, family_lines, fromfile=mir_label, tofile=family_label
    ))
    if diff_ab:
        print("".join(diff_ab), end="")
    else:
        print("(no diff)")

    print("=== Mir HEAD vs ledger-baseline ===")
    diff_ac = list(difflib.unified_diff(
        mir_lines, baseline_lines, fromfile=mir_label, tofile=baseline_label
    ))
    if diff_ac:
        print("".join(diff_ac), end="")
    else:
        print("(no diff)")


def write_harness_config(family_root: Path, family_slug: str, mir_root: Path) -> None:
    """Write/update <family-root>/.mir/harness-config.json as a sync copy of the central catalog config/repos/<family_slug>.json entry.

    Phase C — each repository carries its own harness JSON synced from the central catalog.
    """
    try:
        catalog = load_catalog(mir_root)
    except FileNotFoundError:
        return

    entry = None
    for repo in catalog.get("repositories", []):
        if repo.get("slug") == family_slug:
            entry = repo
            break

    if entry is None:
        return

    mir_head = get_mir_head_commit()
    now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    catalog_revision = "v3.6"
    catalog_version = catalog.get("version", 2)

    payload = {
        "version": 1,
        "family_slug": family_slug,
        "catalog_version": catalog_version,
        "catalog_revision": catalog_revision,
        "last_synced_from_upstream_at": now_utc,
        "last_synced_upstream_commit": mir_head,
        "repository_type": entry.get("repository_type"),
        "overlay_archetype": entry.get("overlay_archetype"),
        "orchestration_profile": entry.get("orchestration_profile"),
        "active_agents": entry.get("active_agents", []),
        "active_skills": entry.get("active_skills", []),
        "agent_overrides": entry.get("agent_overrides", {}),
        "skill_overrides": entry.get("skill_overrides", {}),
        "rationale": entry.get("rationale", ""),
        "last_reviewed_at": entry.get("last_reviewed_at", ""),
        "notes": [
            "Local sync copy of upstream config/repos/<family_slug>.json.",
            (
                "Source of truth: this repo's config/repos/<family_slug>.json. "
                "This file MAY be locally edited; harness refresh treats one-way push "
                "(upstream -> family) per the deployment ADR."
            ),
            (
                "Auto-synced by tools/profile_compiler/specialist_deploy.py::"
                "refresh_specialists(apply=True)."
            ),
        ],
    }

    config_path = family_root / ".mir" / "harness-config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def refresh_specialists(
    family_root: Path,
    slugs: list[str],
    *,
    apply: bool = False,
    dry_run: bool = True,
    diff: bool = False,
    accept_family: bool = False,
    family_slug: str | None = None,
) -> dict[str, Any]:
    """Deploy specialist .md files from the host repo to a family repository.

    Parameters
    ----------
    family_root:
        Absolute path to the target family repository root.
    slugs:
        List of specialist slugs to process.
    apply:
        If True, copy files and update ledger. Requires clean Mir working tree
        for each slug.
    dry_run:
        If True (default), do not write any files. Returns would-copy/conflict info.

    Returns
    -------
    dict mapping slug -> {action, drift_status, source_sha256, deployed_sha256, ...}
    """
    active_modes = [m for m in (apply, diff, accept_family) if m]
    if len(active_modes) > 1:
        raise SpecialistDeployError(
            "--apply, --diff, --accept-family are mutually exclusive"
        )

    mir_root = get_mir_root()
    ledger = load_ledger(family_root)
    report: dict[str, Any] = {}
    ledger_dirty: bool = False

    for slug in slugs:
        source_path = mir_root / ".claude" / "agents" / f"{slug}.md"
        deployed_path = family_root / ".claude" / "agents" / f"{slug}.md"

        if not source_path.exists():
            report[slug] = {
                "action": "error",
                "drift_status": "missing_source",
                "error": f"Mir source not found: {source_path}",
            }
            raise SpecialistDeployError(f"Mir source not found for slug '{slug}': {source_path}")

        ledger_entry = ledger["specialists"].get(slug)
        drift_status = classify_drift(ledger_entry, source_path, deployed_path)
        source_sha = compute_normalized_sha256(source_path)

        if diff:
            if drift_status in ("mir_updated", "both_diverged"):
                ledger_entry_for_diff = ledger["specialists"].get(slug)
                print_three_way_diff(slug, mir_root, family_root, ledger_entry_for_diff)
            report[slug] = {
                "action": "diff",
                "drift_status": drift_status,
                "source_sha256": source_sha,
            }
            continue

        if accept_family:
            if drift_status not in ("family_modified", "both_diverged"):
                report[slug] = {
                    "action": "error",
                    "drift_status": drift_status,
                    "error": (
                        "--accept-family only valid when drift is family_modified "
                        f"or both_diverged, got: {drift_status}"
                    ),
                }
                continue
            deployed_sha = (
                compute_normalized_sha256(deployed_path) if deployed_path.exists() else ""
            )
            source_commit = get_mir_head_commit()
            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            ledger["specialists"][slug] = {
                "source_path": f".claude/agents/{slug}.md",
                "source_sha256": source_sha,
                "source_commit": source_commit,
                "deployed_path": f".claude/agents/{slug}.md",
                "deployed_sha256": deployed_sha,
                "deployed_at": now_utc,
                "drift_status": "in_sync",
            }
            report[slug] = {
                "action": "accepted",
                "drift_status": drift_status,
                "source_sha256": source_sha,
                "deployed_sha256": deployed_sha,
            }
            ledger_dirty = True
            continue

        if apply:
            # Abort if Mir working tree is dirty for this file
            if is_mir_dirty(slug):
                raise SpecialistDeployError(
                    f"Mir working tree is dirty for '{slug}'. Commit or stash before deploying.",
                )

            # Idempotent skip on in_sync
            if drift_status == "in_sync":
                report[slug] = {
                    "action": "skipped",
                    "drift_status": "in_sync",
                    "source_sha256": source_sha,
                    "deployed_sha256": source_sha,
                }
                continue

            if drift_status in ("family_modified", "both_diverged"):
                # Conflict — refuse, report
                current_deployed_sha = (
                    compute_normalized_sha256(deployed_path) if deployed_path.exists() else ""
                )
                report[slug] = {
                    "action": "conflict",
                    "drift_status": drift_status,
                    "source_sha256": source_sha,
                    "deployed_sha256": current_deployed_sha,
                    "note": "Family-local file has been modified. Resolve conflict manually before re-running.",
                }
                continue

            # Safe to copy
            deployed_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(str(source_path), str(deployed_path))

            deployed_sha = compute_normalized_sha256(deployed_path)
            source_commit = get_mir_head_commit()
            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            ledger["specialists"][slug] = {
                "source_path": f".claude/agents/{slug}.md",
                "source_sha256": source_sha,
                "source_commit": source_commit,
                "deployed_path": f".claude/agents/{slug}.md",
                "deployed_sha256": deployed_sha,
                "deployed_at": now_utc,
                "drift_status": "in_sync",
            }
            ledger_dirty = True
            report[slug] = {
                "action": "copied",
                "drift_status": drift_status,
                "source_sha256": source_sha,
                "deployed_sha256": deployed_sha,
            }
        else:
            # Dry-run
            current_deployed_sha = (
                compute_normalized_sha256(deployed_path) if deployed_path.exists() else ""
            )
            action = "conflict" if drift_status in ("family_modified", "both_diverged") else "would-copy"
            if drift_status == "in_sync":
                action = "skipped"
            report[slug] = {
                "action": action,
                "drift_status": drift_status,
                "source_sha256": source_sha,
                "deployed_sha256": current_deployed_sha,
            }

    if (apply or accept_family) and ledger_dirty:
        write_ledger(family_root, ledger)

    if apply and family_slug is not None:
        mir_root = get_mir_root()
        write_harness_config(family_root, family_slug, mir_root)

    return report
