#!/usr/bin/env python3
"""Composite TDD ledger validator for hook enforcement.

tier: block — TDD obligation enforcement (R27-T02 / Choice 5=A).
Python hooks use Tier enum from src.mir.core.engine.hook_chain.
Shell callers: _MIR_HOOK_TIER=block is documented here for cross-reference.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MANDATORY_CATEGORIES = [
    "unit",
    "integration",
    "e2e",
    "browser",
    "edge",
    "architecture",
    "availability",
    "load",
    "soak",
    "security",
    "compatibility",
    "transaction_locking",
]

IMPLEMENTATION_SUFFIXES = (
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".swift",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".sql",
)

PREWRITE_ALLOWED = {"planned", "pass", "covered_existing", "not_applicable"}
PRECOMMIT_ALLOWED = {"pass", "covered_existing", "not_applicable"}


def normalize_path(project_dir: Path, raw: str) -> str:
    path = raw.strip()
    if not path:
        return path
    path = path.replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    project = str(project_dir).replace("\\", "/")
    if path.startswith(project + "/"):
        path = path[len(project) + 1 :]
    return path


def load_ledger(project_dir: Path) -> dict:
    ledger_path = project_dir / "tasks" / "tdd.json"
    if not ledger_path.is_file():
        raise SystemExit(
            "[TddGuard BLOCK] Missing tasks/tdd.json. Create the composite TDD "
            "ledger before editing code."
        )
    try:
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[TddGuard BLOCK] Malformed tasks/tdd.json: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("[TddGuard BLOCK] tasks/tdd.json must contain a JSON object.")
    changes = data.get("changes")
    if not isinstance(changes, list):
        raise SystemExit("[TddGuard BLOCK] tasks/tdd.json must contain a 'changes' array.")
    return data


def matches_target(target: str, rel_path: str) -> bool:
    target = target.strip()
    if not target:
        return False
    if target.endswith("/"):
        return rel_path.startswith(target)
    return rel_path == target


def is_implementation_path(rel_path: str) -> bool:
    if not rel_path.startswith(("src/", "app/", "lib/")):
        return False
    return rel_path.endswith(IMPLEMENTATION_SUFFIXES)


def find_change(data: dict, rel_path: str) -> dict | None:
    for change in data.get("changes", []):
        if not isinstance(change, dict):
            continue
        # Support both legacy singular "target" and current plural "targets" array.
        target = change.get("target")
        if isinstance(target, str) and matches_target(target, rel_path):
            return change
        targets = change.get("targets")
        if isinstance(targets, list):
            if any(isinstance(t, str) and matches_target(t, rel_path) for t in targets):
                return change
    return None


def require_str(mapping: dict, key: str, *, prefix: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"{prefix} Missing '{key}' for target.")
    return value.strip()


def validate_change(change: dict, *, phase: str) -> list[str]:
    prefix = "[TddGuard BLOCK]" if phase == "prewrite" else "[PreCommitVerification BLOCK]"
    # Legacy flat-entry schema: require target/bluebrick/design_ref.
    # Current composite schema uses "targets" array + "scope" instead — skip legacy fields.
    if "targets" not in change:
        require_str(change, "target", prefix=prefix)
        require_str(change, "bluebrick", prefix=prefix)
        require_str(change, "design_ref", prefix=prefix)
    categories = change.get("categories")
    if not isinstance(categories, dict):
        raise SystemExit(f"{prefix} Missing 'categories' object for target {change.get('target')}.")

    commands: list[str] = []
    allowed_statuses = PREWRITE_ALLOWED if phase == "prewrite" else PRECOMMIT_ALLOWED
    # Current composite schema ("targets" array): validate only the categories declared.
    # Legacy schema (singular "target"): require all MANDATORY_CATEGORIES.
    is_composite_schema = "targets" in change
    categories_to_check = list(categories.keys()) if is_composite_schema else MANDATORY_CATEGORIES
    target_label = change.get("target") or change.get("id", "<unknown>")
    for category in categories_to_check:
        entry = categories.get(category)
        if not isinstance(entry, dict):
            raise SystemExit(f"{prefix} Missing category '{category}' for target {target_label}.")
        status = entry.get("status")
        if status not in allowed_statuses:
            if phase == "precommit" and status == "planned":
                raise SystemExit(
                    f"{prefix} Category '{category}' is still planned for target {target_label}."
                )
            raise SystemExit(
                f"{prefix} Invalid status '{status}' for category '{category}' "
                f"in target {target_label}."
            )
        if status == "not_applicable":
            reason = entry.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise SystemExit(
                    f"{prefix} Category '{category}' marked not_applicable without "
                    f"reason for target {target_label}."
                )
        if status in {"pass", "covered_existing"}:
            command = entry.get("command")
            if not isinstance(command, str) or not command.strip():
                raise SystemExit(
                    f"{prefix} Category '{category}' requires a runnable command "
                    f"for target {target_label}."
                )
            commands.append(command.strip())
    return commands


def prewrite(project_dir: Path, target_path: str) -> int:
    rel_path = normalize_path(project_dir, target_path)
    data = load_ledger(project_dir)
    change = find_change(data, rel_path)
    if change is None:
        print(
            f"[TddGuard BLOCK] No composite TDD entry found in tasks/tdd.json for {rel_path}.",
            file=sys.stderr,
        )
        return 2
    validate_change(change, phase="prewrite")
    return 0


def precommit(project_dir: Path, changed_file_list: Path) -> int:
    data = load_ledger(project_dir)
    if not changed_file_list.is_file():
        print("[PreCommitVerification BLOCK] Missing changed-file list input.", file=sys.stderr)
        return 2

    commands: list[str] = []
    seen: set[str] = set()
    for raw in changed_file_list.read_text(encoding="utf-8").splitlines():
        rel_path = normalize_path(project_dir, raw)
        if not rel_path:
            continue
        if not is_implementation_path(rel_path):
            continue
        change = find_change(data, rel_path)
        if change is None:
            print(
                "[PreCommitVerification BLOCK] No composite TDD entry found in "
                f"tasks/tdd.json for {rel_path}.",
                file=sys.stderr,
            )
            return 2
        for command in validate_change(change, phase="precommit"):
            if command not in seen:
                seen.add(command)
                commands.append(command)

    for command in commands:
        print(command)
    return 0


def _git_changed_files(project_dir: Path) -> list[str]:
    """Return list of files changed in current branch vs its merge base.

    Priority:
    1. ``@{upstream}..HEAD`` if upstream exists.
       - If non-empty → return.
       - If empty (HEAD == upstream) → fall through to uncommitted diff.
         Do NOT silently fall back to ``origin/main`` (avoids polluting the
         merge-gate scope with months of unrelated history when the local
         branch is in fact aligned with its tracking branch).
    2. If no upstream: try ``origin/main..HEAD``, then ``main..HEAD``.
    3. Final fallback: uncommitted ``git diff HEAD`` (staged + unstaged).

    Empty list = git unavailable or no diff anywhere.
    """
    import subprocess

    def _run(args: list[str]) -> tuple[int, str]:
        try:
            out = subprocess.run(
                ["git", *args],
                capture_output=True,
                text=True,
                cwd=project_dir,
                check=False,
                timeout=10,
            )
            return out.returncode, out.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return 128, ""

    # Step 1: upstream-aware path.
    rc, output = _run(["diff", "--name-only", "@{upstream}..HEAD"])
    if rc == 0:
        # Upstream exists. Non-empty wins; empty means HEAD == upstream → use uncommitted.
        lines = [line for line in output.splitlines() if line.strip()]
        if lines:
            return lines
        rc2, output2 = _run(["diff", "--name-only", "HEAD"])
        if rc2 == 0:
            return [line for line in output2.splitlines() if line.strip()]
        return []

    # Step 2: no upstream — fall back to common bases.
    for ref in ("origin/main", "main"):
        rc, output = _run(["diff", "--name-only", f"{ref}..HEAD"])
        if rc == 0 and output.strip():
            return [line for line in output.splitlines() if line.strip()]

    # Step 3: uncommitted diff.
    rc, output = _run(["diff", "--name-only", "HEAD"])
    if rc == 0:
        return [line for line in output.splitlines() if line.strip()]
    return []


def precommit_merge(project_dir: Path) -> int:
    """ADR-07 Phase 7B — pre-merge gate hook delegate.

    Scoped to entries whose ``targets`` overlap files changed in the current
    branch (vs ``origin/main`` or ``main``). Pre-existing planned entries
    unrelated to the current PR are grandfathered (review independent C-3 / W3
    mitigation — legacy ledger entries should not block unrelated merges).

    Returns 0 when:
    - The PR touches no files referenced by any tdd.json entry, OR
    - Every entry whose targets overlap PR changed files has all categories
      in the closed-status set (``pass`` / ``covered_existing`` /
      ``not_applicable``).

    Returns 2 (block) when an entry covering one of the PR's changed files has
    any category status outside the closed set.
    """
    data = load_ledger(project_dir)
    closed_categories = {"pass", "covered_existing", "not_applicable"}
    closed_top_level = {"closed", "done"}
    changed = _git_changed_files(project_dir)
    if not changed:
        # No diff visible; conservative pass — git unavailable or no changes.
        return 0
    blockers: list[str] = []
    legacy_warn: list[str] = []

    # Meta-ledger paths are excluded from relevance check — every entry lists
    # these as targets but they are not source/test artifacts whose closure
    # signals readiness for merge (review independent verification W3 v3).
    _META_PATHS = {
        "tasks/tdd.json",
        "tasks/plan.md",
        "tasks/checklist.md",
        "tasks/change_log.md",
        "tasks/lessons.md",
        "tasks/cost-log.md",
        "docs/memory-map.md",
    }
    code_changed = [
        c
        for c in changed
        if c not in _META_PATHS
        and not c.startswith("tasks/sessions/")
        and not c.startswith("tasks/log/")
        and not c.startswith("tasks/handoffs/")
    ]

    for change in data.get("changes", []):
        cid = change.get("id", "<unnamed>")
        targets = change.get("targets", [])
        # Only consider non-meta source/test targets for relevance.
        code_targets = [
            t
            for t in targets
            if t not in _META_PATHS
            and not t.startswith("tasks/sessions/")
            and not t.startswith("tasks/log/")
            and not t.startswith("tasks/handoffs/")
        ]
        relevant = any(matches_target(t, c) for t in code_targets for c in code_changed)
        cats = change.get("categories", {})
        cat_violations: list[str] = []
        for cat_name, cat_body in cats.items():
            if not isinstance(cat_body, dict):
                continue
            status = cat_body.get("status")
            if status not in closed_categories:
                cat_violations.append(f"{cat_name}.status={status!r}")
        if not cat_violations:
            continue
        if relevant:
            blockers.append(f"{cid}: " + ", ".join(cat_violations))
        else:
            legacy_warn.append(cid)

    for key, value in data.items():
        if key in {"version", "changes"}:
            continue
        if isinstance(value, dict):
            status = value.get("status")
            if status is not None and status not in closed_top_level:
                # Legacy top-level (P0-* / P2-*) — warn, do not block.
                legacy_warn.append(f"{key}.status={status!r}")

    if legacy_warn:
        print(
            "[pre-merge-gate INFO] legacy/un-touched tdd entries with open categories"
            f" (grandfathered, not blocking): {len(legacy_warn)}",
            file=sys.stderr,
        )

    if blockers:
        print(
            "[pre-merge-gate BLOCK] tdd.json has open categories for files in this PR:\n  - "
            + "\n  - ".join(blockers),
            file=sys.stderr,
        )
        return 2
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: tdd-matrix-guard.py <prewrite|precommit|precommit-merge> "
            "<project_dir> [<target>]",
            file=sys.stderr,
        )
        return 2
    mode = argv[0]
    project_dir = Path(argv[1]).resolve()
    if mode == "precommit-merge":
        return precommit_merge(project_dir)
    if len(argv) < 3:
        print(
            "usage: tdd-matrix-guard.py <prewrite|precommit> <project_dir> <target>",
            file=sys.stderr,
        )
        return 2
    target = argv[2]
    if mode == "prewrite":
        return prewrite(project_dir, target)
    if mode == "precommit":
        return precommit(project_dir, Path(target))
    print(f"unknown mode: {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
