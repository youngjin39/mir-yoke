"""Read-only task-context selection from the repository profile.

This module does not load referenced file bodies or persist state.  It turns the
existing ``.mir/repo-profile.toml`` overlay into a compact index for ADR-53's
single on-demand retrieval surface.
"""
from __future__ import annotations

import fnmatch
import re
import subprocess
import tomllib
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

_REFERENCE_FIELDS = (
    ("architecture", "architecture_refs"),
    ("configuration", "configuration_paths"),
    ("verification", "verification_paths"),
    ("workflow", "workflow_refs"),
    ("exception", "exception_refs"),
)
_REFERENCE_KINDS = {kind for kind, _ in _REFERENCE_FIELDS}
_PROFILE_PATH_KINDS = _REFERENCE_KINDS | {"code_scope", "non_code_scope"}
_GROUP_TERMS = {
    "code": {
        "bug",
        "code",
        "implementation",
        "script",
        "source",
        "src",
        "tool",
        "tools",
    },
    "documentation": {"adr", "design", "doc", "docs", "readme"},
    "configuration": {
        "config",
        "configuration",
        "json",
        "profile",
        "settings",
        "toml",
        "yaml",
    },
    "verification": {"test", "tests", "tdd", "validation", "verify"},
    "workflow": {
        "dispatch",
        "hook",
        "merge",
        "process",
        "workflow",
    },
    "exception": {
        "exception",
        "production",
        "protected",
        "release",
        "risk",
        "runtime",
        "secret",
    },
}
_FULL_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _normalise_repo_path(value: str) -> str | None:
    candidate = value.strip().replace("\\", "/")
    while candidate.startswith("./"):
        candidate = candidate[2:]
    pure = PurePosixPath(candidate)
    if not candidate or pure.is_absolute() or ".." in pure.parts:
        return None
    return candidate


def _path_matches(scope: str, target: str) -> bool:
    scope_norm = _normalise_repo_path(scope)
    target_norm = _normalise_repo_path(target)
    if scope_norm is None or target_norm is None:
        return False
    if any(char in scope_norm for char in "*?["):
        if fnmatch.fnmatch(target_norm, scope_norm):
            return True
        prefix = scope_norm.split("*", 1)[0].rstrip("/")
        return bool(prefix) and (
            target_norm == prefix or target_norm.startswith(f"{prefix}/")
        )
    scope_base = scope_norm.rstrip("/")
    target_base = target_norm.rstrip("/")
    return (
        target_base == scope_base
        or target_base.startswith(f"{scope_base}/")
        or scope_base.startswith(f"{target_base}/")
    )


def _query_terms(query: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[^\W_]+", query.casefold(), flags=re.UNICODE)
        if len(token) > 1
    }


def _query_matches_ref(terms: set[str], kind: str, path: str) -> bool:
    haystack = f"{kind} {path}".casefold()
    return any(term in haystack for term in terms if len(term) >= 3)


def _reference_state(root: Path, path: str) -> str:
    """Classify one profile pointer without reading its body."""
    try:
        if any(char in path for char in "*?["):
            matches = list(root.glob(path))
            if not matches:
                return "missing"
            candidates = matches
        else:
            candidate = root / path
            candidates = [candidate]
            if not candidate.exists():
                return "missing"
        for candidate in candidates:
            candidate.resolve().relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return "unsafe"
    if len(candidates) == 1 and candidates[0].is_file():
        return "file"
    return "container"


def _git_output(root: Path, args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def _git_paths(root: Path, args: list[str]) -> list[str]:
    """Read Git paths losslessly; ``-z`` disables quote-path escaping."""
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [
        raw.decode("utf-8", errors="surrogateescape")
        for raw in proc.stdout.split(b"\0")
        if raw
    ]


def _changed_paths(root: Path, base_commit: str) -> list[str]:
    commands = (
        ["diff", "--name-only", "-z", f"{base_commit}..HEAD"],
        ["diff", "--name-only", "-z"],
        ["diff", "--cached", "--name-only", "-z"],
        ["ls-files", "--others", "--exclude-standard", "-z"],
    )
    changed: set[str] = set()
    for args in commands:
        changed.update(_git_paths(root, args))
    return sorted(changed)


def _freshness(
    root: Path,
    base_commit: str,
    selected_paths: Iterable[str],
) -> dict[str, Any]:
    selected = tuple(dict.fromkeys(selected_paths))
    result: dict[str, Any] = {
        "state": "unverified",
        "base_commit": base_commit or "unverified",
        "head": "",
        "changed_selected": [],
        "changed_selected_count": 0,
        "reason": "profile baseline is unverified",
    }
    code, head = _git_output(root, ["rev-parse", "HEAD"])
    if code != 0:
        result["reason"] = "repository HEAD is unavailable"
        return result
    result["head"] = head

    if not _FULL_COMMIT_RE.fullmatch(base_commit):
        return result
    code, _ = _git_output(root, ["cat-file", "-e", f"{base_commit}^{{commit}}"])
    if code != 0:
        result.update(state="uncertain", reason="profile baseline commit is unavailable")
        return result
    code, _ = _git_output(root, ["merge-base", "--is-ancestor", base_commit, "HEAD"])
    if code != 0:
        result.update(state="uncertain", reason="profile baseline is not an ancestor of HEAD")
        return result

    changed = _changed_paths(root, base_commit)
    changed_selected = sorted(
        path for path in changed if any(_path_matches(scope, path) for scope in selected)
    )
    result["changed_selected"] = changed_selected[:50]
    result["changed_selected_count"] = len(changed_selected)
    if changed_selected:
        result.update(
            state="review_required",
            reason="task-selected paths changed since the profile baseline",
        )
    elif head == base_commit:
        result.update(state="current", reason="selected paths match the profile baseline")
    else:
        result.update(
            state="current_for_selection",
            reason="HEAD advanced without changes to task-selected paths",
        )
    return result


def _empty_invalid_context(query: str, risk: str, warning: str) -> dict[str, Any]:
    return {
        "repository": {
            "slug": "unknown",
            "repository_type": "unknown",
            "purpose": "",
            "technology_stack": [],
        },
        "task": {"query": query, "risk": risk, "target_paths": []},
        "safety": {
            "protected_paths": [],
            "generated_paths": [],
            "preserve": {},
            "boundaries": {},
            "gates": {},
        },
        "selected_refs": [],
        "freshness": {
            "state": "uncertain",
            "base_commit": "unverified",
            "head": "",
            "changed_selected": [],
            "reason": warning,
        },
        "needs_investigation": True,
        "warnings": [warning],
    }


def build_profile_task_context(
    project_root: Path,
    *,
    query: str,
    target_paths: tuple[str, ...] = (),
    risk: str = "normal",
) -> dict[str, Any] | None:
    """Return a compact profile index for one task, or ``None`` if absent.

    ``risk`` is an explicit main-agent classification.  The selector never
    infers authorization or blocks execution; stale/uncertain evidence only
    requests incremental investigation.
    """
    if risk not in {"low", "normal", "high"}:
        raise ValueError(f"unsupported task risk: {risk!r}")
    root = Path(project_root).resolve()
    profile_path = root / ".mir" / "repo-profile.toml"
    if not profile_path.is_file():
        return None
    try:
        with profile_path.open("rb") as handle:
            profile = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return _empty_invalid_context(query, risk, f"repository profile is unreadable: {exc}")

    repo = profile.get("repo") if isinstance(profile.get("repo"), dict) else {}
    paths = profile.get("paths") if isinstance(profile.get("paths"), dict) else {}
    preserve = profile.get("preserve") if isinstance(profile.get("preserve"), dict) else {}
    boundaries = (
        profile.get("boundaries") if isinstance(profile.get("boundaries"), dict) else {}
    )
    gates = profile.get("gates") if isinstance(profile.get("gates"), dict) else {}

    warnings: list[str] = []
    valid_targets: list[str] = []
    for target in target_paths:
        normalised = _normalise_repo_path(target)
        if normalised is None:
            warnings.append(f"ignored non-repository target path: {target}")
        else:
            valid_targets.append(normalised)

    safety_scopes = (
        ("protected path", _string_list(paths.get("protected_paths"))),
        ("generated path", _string_list(paths.get("generated_paths"))),
        (
            "preserve path",
            [
                *_string_list(preserve.get("agent_memory_paths")),
                *_string_list(preserve.get("extra_docs")),
            ],
        ),
        ("live runtime boundary", _string_list(boundaries.get("live_runtime"))),
        ("secret path", _string_list(boundaries.get("secrets"))),
    )
    for target in valid_targets:
        for label, scopes in safety_scopes:
            if any(_path_matches(scope, target) for scope in scopes):
                warnings.append(f"target intersects {label}: {target}")

    groups: dict[str, list[str]] = {}
    for kind, field in _REFERENCE_FIELDS:
        refs: list[str] = []
        for candidate in _string_list(paths.get(field)):
            normalised = _normalise_repo_path(candidate)
            if normalised is None:
                warnings.append(f"ignored invalid profile reference: {field}={candidate}")
            else:
                refs.append(normalised)
        groups[kind] = refs

    code_scopes = [
        path
        for item in _string_list(paths.get("code_paths"))
        if (path := _normalise_repo_path(item)) is not None
    ]
    non_code_scopes = [
        path
        for item in _string_list(paths.get("non_code_paths"))
        if (path := _normalise_repo_path(item)) is not None
    ]
    terms = _query_terms(query)
    signalled = {
        group for group, keywords in _GROUP_TERMS.items() if terms & keywords
    }

    selected: list[dict[str, str]] = []

    def add(kind: str, values: Iterable[str]) -> None:
        for value in values:
            item = {"kind": kind, "path": value}
            if item not in selected:
                selected.append(item)

    # Small profile default: architecture pointers, identity, and stack only.
    add("architecture", groups["architecture"])
    for kind, refs in groups.items():
        add(kind, (ref for ref in refs if _query_matches_ref(terms, kind, ref)))

    matched_target = False
    for target in valid_targets:
        matching_code = [scope for scope in code_scopes if _path_matches(scope, target)]
        matching_non_code = [
            scope for scope in non_code_scopes if _path_matches(scope, target)
        ]
        matching_config = [
            ref for ref in groups["configuration"] if _path_matches(ref, target)
        ]
        matching_verify = [
            ref for ref in groups["verification"] if _path_matches(ref, target)
        ]
        matching_workflow = [
            ref for ref in groups["workflow"] if _path_matches(ref, target)
        ]
        matching_exception = [
            ref for ref in groups["exception"] if _path_matches(ref, target)
        ]
        if matching_code:
            matched_target = True
            add("code_scope", matching_code)
            add("verification", groups["verification"])
        if matching_non_code:
            matched_target = True
            add("non_code_scope", matching_non_code)
            add("workflow", groups["workflow"])
        if matching_config:
            matched_target = True
            add("configuration", matching_config)
            add("workflow", groups["workflow"])
            add("verification", groups["verification"])
        if matching_verify:
            matched_target = True
            add("verification", matching_verify)
        if matching_workflow:
            matched_target = True
            add("workflow", matching_workflow)
        if matching_exception:
            matched_target = True
            add("exception", matching_exception)

    if "code" in signalled:
        add("code_scope", code_scopes)
        add("verification", groups["verification"])
    if "documentation" in signalled:
        add("non_code_scope", non_code_scopes)
        add("workflow", groups["workflow"])
    for kind in ("configuration", "verification", "workflow", "exception"):
        if kind in signalled:
            add(kind, groups[kind])
    if "configuration" in signalled:
        add("workflow", groups["workflow"])
    if risk == "high":
        add("workflow", groups["workflow"])
        add("exception", groups["exception"])
        add("verification", groups["verification"])

    exact_reference_paths: list[str] = []
    container_reference_paths: list[str] = []
    safe_selected: list[dict[str, str]] = []
    for item in selected:
        if item["kind"] not in _PROFILE_PATH_KINDS:
            safe_selected.append(item)
            continue
        state = _reference_state(root, item["path"])
        path_kind = "reference" if item["kind"] in _REFERENCE_KINDS else "scope"
        if state == "unsafe":
            warnings.append(f"ignored unsafe profile {path_kind}: {item['path']}")
            continue
        if state == "missing":
            warnings.append(
                f"selected profile {path_kind} is missing: {item['path']}"
            )
        elif state == "file":
            exact_reference_paths.append(item["path"])
        elif state == "container":
            container_reference_paths.append(item["path"])
        safe_selected.append(item)
    selected = safe_selected

    # Directory references are lookup roots, not claims that every descendant is
    # unchanged. Explicit targets and exact canonical files define freshness.
    selected_paths = exact_reference_paths + valid_targets
    base_commit = str(repo.get("profile_base_commit", "unverified")).strip().lower()
    freshness = _freshness(root, base_commit, selected_paths)
    if (
        not valid_targets
        and container_reference_paths
        and freshness["state"] in {"current", "current_for_selection"}
    ):
        freshness.update(
            state="unverified_for_selection",
            reason=(
                "query selected directory lookup roots without a concrete target; "
                "inspect only the relevant descendant"
            ),
        )
    selection_confident = matched_target or bool(signalled) or risk == "high"
    needs_investigation = (
        not selection_confident
        or freshness["state"]
        in {"unverified", "unverified_for_selection", "uncertain", "review_required"}
        or bool(warnings)
    )

    return {
        "repository": {
            "slug": str(repo.get("slug", "unknown")),
            "repository_type": str(repo.get("repository_type", "unknown")),
            "purpose": str(repo.get("purpose", "")),
            "technology_stack": _string_list(repo.get("technology_stack")),
            "profile_verified_at": str(repo.get("profile_verified_at", "")),
        },
        "task": {
            "query": query,
            "risk": risk,
            "target_paths": valid_targets,
        },
        "safety": {
            "protected_paths": _string_list(paths.get("protected_paths")),
            "generated_paths": _string_list(paths.get("generated_paths")),
            "preserve": preserve,
            "boundaries": boundaries,
            "gates": gates,
        },
        "selected_refs": selected,
        "freshness": freshness,
        "needs_investigation": needs_investigation,
        "warnings": warnings,
    }


__all__ = ("build_profile_task_context",)
