"""Preservation-first readiness checks for an existing Mir repository."""

from __future__ import annotations

import argparse
import hashlib
import importlib.resources
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import yaml

from mir.core.engine.memory.distill import sanitize_fts_query

from ._changes import changed_paths, snapshot_project
from .bootstrap import _scan_content_candidates

_SURFACE_KEYS = (
    "bootstrap_start_gate",
    "project_profile",
    "identity_finalize",
    "managed_python_launcher",
    "content_onboarding",
    "memory_acceptance",
    "phase2_spec",
)
_DISPOSITIONS = {"applied", "repository_owned", "not_applicable", "exception"}
_REQUIRED_RUNTIME_EVIDENCE = {
    "bootstrap_start_gate": (
        ".claude/hooks/_lib/bootstrap-gate.sh",
        ".claude/hooks/session-start.sh",
        ".claude/hooks/pre-tool-use.sh",
        ".claude/settings.json",
        ".codex/hooks.json",
    ),
    "managed_python_launcher": (
        ".claude/hooks/_lib/run-python.sh",
        ".claude/hooks/session-start.sh",
        ".claude/hooks/pre-tool-use.sh",
    ),
}
_DIRECT_PROFILE_MAP = {
    "code_app": "code_app",
    "code_product": "code_app",
    "hybrid_pipeline": "hybrid_pipeline",
    "content_workspace": "content_workspace",
    "infra_runtime": "infra_runtime",
    "learning_workspace": "content_workspace",
    "meta_harness": "meta_harness",
    "template_transitional": "template_transitional",
    "public_harness_template": "template_transitional",
}
_ARCHETYPE_PROFILE_MAP = {
    "app_product_flutter": "code_app",
    "code_app": "code_app",
    "code_product": "code_app",
    "command_memory_heavy_app": "code_app",
    "hybrid_pipeline": "hybrid_pipeline",
    "infra_runtime": "infra_runtime",
    "learning_low_code": "content_workspace",
    "ontology_content": "content_workspace",
    "meta_harness": "meta_harness",
    "template_transitional": "template_transitional",
}
_PLACEHOLDER_RE = re.compile(r"\b(?:describe|placeholder|replace[ -]?me|tbd|todo|unknown)\b", re.I)
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_LAYER_KEYS = ("l1", "l2", "l3", "l4")
_COUNT_KEYS = ("total", "filled", "derived", "na", "tbd")
_REVIEW_KEYS = (
    "project_structure",
    "memory",
    "discoverability",
    "requirements",
    "organization",
)
_RAW_PYTHON_RE = re.compile(
    r"(?:^|[;&|]\s*|\bexec\s+)(?:/usr/bin/)?python3?(?:\s|$)"
)
_RESOLVED_PLACEHOLDER_COUNT_RE = re.compile(
    r'''["']?(?:tbd|todo)["']?\s*[:=]\s*0\b\s*,?''', re.I
)
_SOURCE_ROOT = Path(__file__).resolve().parents[3]
_PACKAGED_CANONICAL = {
    ".claude/hooks/_lib/bootstrap-gate.sh": "resources/hooks/bootstrap-gate.sh",
    ".claude/hooks/_lib/run-python.sh": "resources/hooks/run-python.sh",
}


class AdoptionError(ValueError):
    """The tracked adoption contract or its live evidence is invalid."""


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mir bootstrap-adoption")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--apply",
        action="store_true",
        help="atomically write a ready bootstrap receipt after every check passes",
    )
    parser.add_argument("--json", action="store_true", dest="json")
    return parser.parse_args(argv)


def _load_json_bytes(path: Path) -> tuple[dict[str, object], bytes]:
    try:
        body = path.read_bytes()
        raw = json.loads(body)
    except (OSError, json.JSONDecodeError) as exc:
        raise AdoptionError(f"invalid {path.as_posix()}: {exc}") from exc
    if not isinstance(raw, dict):
        raise AdoptionError(f"{path.as_posix()} must contain a JSON object")
    return raw, body


def _tracked_path(root: Path, relative: object, *, label: str) -> tuple[Path, str]:
    if not isinstance(relative, str) or not relative.strip():
        raise AdoptionError(f"{label} must be a non-empty project-relative path")
    authored = Path(relative)
    if authored.is_absolute() or ".." in authored.parts:
        raise AdoptionError(f"{label} must stay inside the project: {relative!r}")
    resolved = (root / authored).resolve(strict=False)
    try:
        normalized = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise AdoptionError(f"{label} escapes the project: {relative!r}") from exc
    return resolved, normalized


def _is_git_tracked(root: Path, relative: str) -> bool:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", relative],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
    )
    return result.returncode == 0


def _non_placeholder_text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdoptionError(f"{label} must be a non-empty string")
    value = value.strip()
    if _PLACEHOLDER_RE.search(value):
        raise AdoptionError(f"{label} must not contain placeholder text")
    return value


def _contains_unresolved_placeholder(body: str) -> bool:
    return any(
        _PLACEHOLDER_RE.search(_RESOLVED_PLACEHOLDER_COUNT_RE.sub("", line))
        for line in body.splitlines()
    )


def _validate_profile(
    root: Path, manifest: dict[str, object]
) -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    path = root / ".mir/repo-profile.toml"
    try:
        with path.open("rb") as handle:
            profile = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"invalid .mir/repo-profile.toml: {exc}"], {}

    repo = profile.get("repo")
    if not isinstance(repo, dict):
        return [".mir/repo-profile.toml must contain [repo]"], {}
    slug = repo.get("slug")
    repository_type = repo.get("repository_type")
    archetype = repo.get("overlay_archetype")
    selected_slug = manifest.get("project_slug")
    selected_archetype = manifest.get("repository_archetype")
    selected_profile = manifest.get("profile")

    if not isinstance(slug, str) or not _SLUG_RE.fullmatch(slug):
        errors.append("[repo].slug must be a concrete lowercase project slug")
    elif selected_slug != slug:
        errors.append(
            f"adoption project_slug {selected_slug!r} does not match [repo].slug {slug!r}"
        )
    if not isinstance(archetype, str) or not archetype:
        errors.append("[repo].overlay_archetype must be non-empty")
    elif selected_archetype != archetype:
        errors.append(
            "adoption repository_archetype does not match "
            f"[repo].overlay_archetype {archetype!r}"
        )

    mapped = (
        _DIRECT_PROFILE_MAP.get(repository_type)
        if isinstance(repository_type, str)
        else None
    )
    if mapped is None and isinstance(archetype, str):
        mapped = _ARCHETYPE_PROFILE_MAP.get(archetype)
    if mapped is None:
        errors.append(
            "cannot map [repo].repository_type/[repo].overlay_archetype to an "
            "existing-repository adoption profile"
        )
    elif selected_profile != mapped:
        errors.append(
            f"repository identity maps to profile {mapped!r}, not {selected_profile!r}"
        )

    purpose = repo.get("purpose")
    stack = repo.get("technology_stack")
    try:
        _non_placeholder_text(purpose, label="[repo].purpose")
    except AdoptionError as exc:
        errors.append(str(exc))
    if not isinstance(stack, list) or not stack:
        errors.append("[repo].technology_stack must be a non-empty array")
    else:
        for index, item in enumerate(stack):
            try:
                _non_placeholder_text(item, label=f"[repo].technology_stack[{index}]")
            except AdoptionError as exc:
                errors.append(str(exc))

    return errors, {
        "project_slug": slug,
        "repository_type": repository_type,
        "overlay_archetype": archetype,
        "mapped_profile": mapped,
        "purpose": purpose,
        "technology_stack": stack,
    }


def _validate_surface_contract(
    root: Path, manifest: dict[str, object]
) -> tuple[list[str], dict[str, dict[str, object]], list[dict[str, object]]]:
    errors: list[str] = []
    surfaces = manifest.get("surfaces")
    if not isinstance(surfaces, dict):
        return ["adoption manifest must contain a surfaces object"], {}, []
    actual = set(surfaces)
    expected = set(_SURFACE_KEYS)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        errors.append(f"adoption surfaces must be exact; missing={missing}, extra={extra}")

    normalized: dict[str, dict[str, object]] = {}
    exceptions: list[dict[str, object]] = []
    for key in _SURFACE_KEYS:
        raw = surfaces.get(key)
        if not isinstance(raw, dict):
            errors.append(f"surface {key!r} must be an object")
            continue
        disposition = raw.get("disposition")
        evidence_paths = raw.get("evidence_paths")
        allowed_keys = {"disposition", "evidence_paths", "reason", "blockers"}
        if key == "memory_acceptance":
            allowed_keys.add("queries")
        elif key == "phase2_spec":
            allowed_keys.update(
                {"coverage", "ai_ready", "open_gaps", "full_review", "native_evidence"}
            )
        extra_keys = sorted(set(raw) - allowed_keys)
        if extra_keys:
            errors.append(f"surface {key!r} has unknown fields: {extra_keys}")
        if disposition not in _DISPOSITIONS:
            errors.append(f"surface {key!r} has invalid disposition {disposition!r}")
            continue
        if not isinstance(evidence_paths, list) or any(
            not isinstance(item, str) or not item.strip() for item in evidence_paths
        ):
            errors.append(f"surface {key!r} evidence_paths must be an array of paths")
            continue
        if len(set(evidence_paths)) != len(evidence_paths):
            errors.append(f"surface {key!r} evidence_paths must be unique")
        if disposition in {"applied", "repository_owned", "exception"} and not evidence_paths:
            errors.append(f"surface {key!r} disposition {disposition!r} requires evidence_paths")

        paths: list[str] = []
        for index, relative in enumerate(evidence_paths):
            try:
                path, normalized_path = _tracked_path(
                    root, relative, label=f"surface {key!r} evidence_paths[{index}]"
                )
            except AdoptionError as exc:
                errors.append(str(exc))
                continue
            paths.append(normalized_path)
            if path.is_symlink() or not path.is_file():
                errors.append(f"surface {key!r} evidence path is missing: {normalized_path}")
                continue
            if not _is_git_tracked(root, normalized_path):
                errors.append(
                    f"surface {key!r} evidence path is not tracked: {normalized_path}"
                )
            try:
                if not path.read_bytes().strip():
                    errors.append(f"surface {key!r} evidence path is empty: {normalized_path}")
            except OSError as exc:
                errors.append(f"surface {key!r} evidence path is unreadable: {exc}")

        row = dict(raw)
        row["evidence_paths"] = paths
        normalized[key] = row
        if disposition == "exception":
            try:
                reason = _non_placeholder_text(raw.get("reason"), label=f"surface {key!r} reason")
            except AdoptionError as exc:
                errors.append(str(exc))
                reason = raw.get("reason")
            blockers = raw.get("blockers")
            if not isinstance(blockers, list) or not blockers:
                errors.append(f"surface {key!r} exception requires non-empty blockers")
                blockers = []
            else:
                for index, blocker in enumerate(blockers):
                    try:
                        _non_placeholder_text(
                            blocker, label=f"surface {key!r} blockers[{index}]"
                        )
                    except AdoptionError as exc:
                        errors.append(str(exc))
            exceptions.append(
                {
                    "surface": key,
                    "reason": reason,
                    "blockers": blockers,
                    "evidence_paths": paths,
                }
            )
        elif disposition == "not_applicable":
            try:
                _non_placeholder_text(raw.get("reason"), label=f"surface {key!r} reason")
            except AdoptionError as exc:
                errors.append(str(exc))
            if key != "content_onboarding":
                errors.append(
                    f"surface {key!r} cannot be not_applicable; use a documented exception"
                )
    return errors, normalized, exceptions


def _hook_commands(document: object) -> list[str]:
    commands: list[str] = []
    if isinstance(document, dict):
        for key, value in document.items():
            if key == "command" and isinstance(value, str):
                commands.append(value)
            else:
                commands.extend(_hook_commands(value))
    elif isinstance(document, list):
        for value in document:
            commands.extend(_hook_commands(value))
    return commands


def _validate_bootstrap_gate(root: Path) -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    paths = {
        "helper": ".claude/hooks/_lib/bootstrap-gate.sh",
        "session": ".claude/hooks/session-start.sh",
        "mutation": ".claude/hooks/pre-tool-use.sh",
        "claude_wiring": ".claude/settings.json",
        "codex_wiring": ".codex/hooks.json",
    }
    bodies: dict[str, str] = {}
    for label, relative in paths.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"bootstrap gate {label} is missing: {relative}")
            continue
        try:
            bodies[label] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"bootstrap gate {label} is unreadable: {exc}")

    helper = bodies.get("helper", "")
    session = bodies.get("session", "")
    mutation = bodies.get("mutation", "")
    if "mir_bootstrap_gate_state" not in helper or "mir_bootstrap_gate_enforce" not in helper:
        errors.append("bootstrap gate helper does not expose state and enforcement functions")
    if "bootstrap-gate.sh" not in session or "mir_bootstrap_gate_state" not in session:
        errors.append("bootstrap gate is not wired into SessionStart")
    if "bootstrap-gate.sh" not in mutation or "mir_bootstrap_gate_enforce" not in mutation:
        errors.append("bootstrap gate is not wired into the mutation hook")

    for runtime, relative, session_name, mutation_name in (
        ("Claude", paths["claude_wiring"], "session-start.sh", "pre-tool-use.sh"),
        ("Codex", paths["codex_wiring"], "session-start.sh", "pre-tool-use.sh"),
    ):
        if not (root / relative).is_file():
            continue
        try:
            raw = json.loads((root / relative).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"bootstrap gate {runtime} wiring is invalid JSON: {exc}")
            continue
        commands = _hook_commands(raw)
        if not any(session_name in command for command in commands):
            errors.append(f"bootstrap gate SessionStart is not active in {runtime} wiring")
        if not any(mutation_name in command for command in commands):
            errors.append(f"bootstrap gate mutation hook is not active in {runtime} wiring")
    return errors, {"status": "pass" if not errors else "fail", "paths": paths}


def _validate_canonical_applied_helper(
    root: Path, relative: str, *, label: str
) -> tuple[list[str], dict[str, object]]:
    target_path = root / relative
    try:
        source_path = _SOURCE_ROOT / relative
        if source_path.is_file():
            source_bytes = source_path.read_bytes()
        else:
            resource = _PACKAGED_CANONICAL.get(relative)
            if resource is None:
                raise OSError(f"no packaged canonical resource for {relative}")
            source_bytes = importlib.resources.files("mir").joinpath(resource).read_bytes()
    except OSError as exc:
        return [f"{label} canonical Mir Yoke source is unreadable: {relative}: {exc}"], {
            "status": "fail",
            "path": relative,
        }
    try:
        target_bytes = target_path.read_bytes()
    except OSError as exc:
        return [f"{label} applied file is unreadable: {relative}: {exc}"], {
            "status": "fail",
            "path": relative,
        }
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    target_hash = hashlib.sha256(target_bytes).hexdigest()
    errors = (
        []
        if source_hash == target_hash
        else [f"{label} does not match Mir Yoke canonical source: {relative}"]
    )
    return errors, {
        "status": "pass" if not errors else "fail",
        "path": relative,
        "source_sha256": source_hash,
        "live_sha256": target_hash,
    }


def _validate_required_runtime_evidence(
    surface: dict[str, object], *, surface_name: str
) -> list[str]:
    declared = set(surface.get("evidence_paths", []))
    return [
        f"{surface_name} must declare runtime evidence path: {relative}"
        for relative in _REQUIRED_RUNTIME_EVIDENCE[surface_name]
        if relative not in declared
    ]


def _has_raw_python(body: str) -> bool:
    return any(
        _RAW_PYTHON_RE.search(line) is not None
        for line in body.splitlines()
        if not line.lstrip().startswith("#")
    )


def _validate_python_launcher(root: Path) -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    relative = ".claude/hooks/_lib/run-python.sh"
    path = root / relative
    try:
        body = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"managed Python launcher is missing or unreadable: {relative}: {exc}"], {}
    for marker in (".venv/bin/python", ".venv/Scripts/python.exe"):
        if marker not in body:
            errors.append(f"managed Python launcher is missing required route {marker!r}")
    has_uv_route = "uv run" in body and "--project" in body
    has_external_route = all(
        marker in body
        for marker in ("bootstrap-receipt.json", "run-python", "--project-root")
    )
    if not (has_uv_route or has_external_route):
        errors.append(
            "managed Python launcher requires either a project uv route or an "
            "external receipt-bound Mir route"
        )
    if _has_raw_python(body.replace("uv run --project", "")):
        errors.append("managed Python launcher contains a host Python fallback")

    wired: list[str] = []
    for hook_relative in (
        ".claude/hooks/session-start.sh",
        ".claude/hooks/pre-tool-use.sh",
    ):
        hook = root / hook_relative
        try:
            hook_body = hook.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"managed Python launcher wiring is unreadable: {hook_relative}: {exc}")
            continue
        if "run-python.sh" not in hook_body:
            errors.append(f"managed Python launcher is not wired into {hook_relative}")
        else:
            wired.append(hook_relative)
        if _has_raw_python(hook_body):
            errors.append(f"managed Python launcher bypass found in {hook_relative}")
    return errors, {
        "status": "pass" if not errors else "fail",
        "launcher": relative,
        "wired_hooks": wired,
    }


def _validate_content_onboarding(
    root: Path, selected_profile: object
) -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    path = root / "config/content-onboarding.json"
    try:
        raw, _ = _load_json_bytes(path)
    except AdoptionError as exc:
        return [str(exc)], {}
    if raw.get("schema_version") != 1:
        errors.append("config/content-onboarding.json schema_version must be 1")
    if raw.get("profile") != "content_workspace":
        errors.append("content onboarding profile must be content_workspace")
    if selected_profile != "content_workspace":
        errors.append("content onboarding is applied to a non-content adoption profile")
    archives = raw.get("archives")
    classified: list[tuple[str, Path]] = []
    if not isinstance(archives, list) or not archives:
        errors.append("content onboarding must contain classified archives")
        archives = []
    for index, archive in enumerate(archives):
        if not isinstance(archive, dict):
            errors.append(f"content onboarding archives[{index}] must be an object")
            continue
        try:
            classification = _non_placeholder_text(
                archive.get("classification"),
                label=f"content onboarding archives[{index}].classification",
            )
            resolved, normalized = _tracked_path(
                root,
                archive.get("path"),
                label=f"content onboarding archives[{index}].path",
            )
        except AdoptionError as exc:
            errors.append(str(exc))
            continue
        if not resolved.exists():
            errors.append(f"classified content archive is missing: {normalized}")
        classified.append((classification, Path(normalized)))
    if len({label for label, _ in classified}) != len(classified):
        errors.append("content onboarding archive classifications must be unique")
    if len({path for _, path in classified}) != len(classified):
        errors.append("content onboarding archive paths must be unique")
    for index, (_, path) in enumerate(classified):
        for _, other in classified[index + 1 :]:
            if path in other.parents or other in path.parents:
                errors.append(
                    "content onboarding archive paths must not overlap: "
                    f"{path.as_posix()!r}, {other.as_posix()!r}"
                )

    scan = raw.get("scan")
    if not isinstance(scan, dict):
        errors.append("content onboarding must contain scan evidence")
    elif scan.get("unclassified") != []:
        errors.append("content onboarding contains unclassified candidates")
    try:
        live_candidates = _scan_content_candidates(root)
    except ValueError as exc:
        errors.append(f"content onboarding live scan failed: {exc}")
        live_candidates = []
    uncovered: list[str] = []
    classified_paths = [path for _, path in classified]
    for candidate in live_candidates:
        candidate_path = Path(str(candidate.get("path", "")))
        if not any(
            candidate_path == classified_path or classified_path in candidate_path.parents
            for classified_path in classified_paths
        ):
            uncovered.append(candidate_path.as_posix())
    if uncovered:
        errors.append(f"content onboarding live scan has unclassified candidates: {uncovered}")
    return errors, {
        "status": "pass" if not errors else "fail",
        "manifest": "config/content-onboarding.json",
        "classifications": [
            {"classification": label, "path": path.as_posix()} for label, path in classified
        ],
        "unclassified": uncovered,
    }


def _validate_memory(
    root: Path, surface: dict[str, object]
) -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    queries = surface.get("queries")
    if not isinstance(queries, list) or not queries:
        return ["memory_acceptance requires at least one live FTS query"], {
            "status": "fail",
            "queries": [],
        }
    db_path = root / ".mir/memory.db"
    if not db_path.is_file():
        return ["memory database is missing: .mir/memory.db"], {
            "status": "fail",
            "queries": [],
        }
    results: list[dict[str, object]] = []
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"{db_path.resolve().as_uri()}?mode=ro&immutable=1",
            uri=True,
        )
        connection.execute("PRAGMA query_only = ON")
        objects = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        required = {
            "external_archives",
            "external_documents",
            "external_chunks",
            "external_chunks_fts",
        }
        missing = sorted(required - objects)
        if missing:
            errors.append(f"memory FTS tables are missing: {missing}")
        else:
            for index, query_spec in enumerate(queries):
                if not isinstance(query_spec, dict):
                    errors.append(f"memory_acceptance queries[{index}] must be an object")
                    continue
                try:
                    archive_slug = _non_placeholder_text(
                        query_spec.get("archive_slug"),
                        label=f"memory_acceptance queries[{index}].archive_slug",
                    )
                    query = _non_placeholder_text(
                        query_spec.get("query"),
                        label=f"memory_acceptance queries[{index}].query",
                    )
                    expected_path = _non_placeholder_text(
                        query_spec.get("expected_path"),
                        label=f"memory_acceptance queries[{index}].expected_path",
                    )
                except AdoptionError as exc:
                    errors.append(str(exc))
                    continue
                row = connection.execute(
                    "SELECT a.slug, a.root_path, d.relative_path "
                    "FROM external_chunks_fts f "
                    "JOIN external_chunks c ON c.id = f.rowid "
                    "JOIN external_documents d ON d.id = c.document_id "
                    "JOIN external_archives a ON a.id = d.archive_id "
                    "WHERE external_chunks_fts MATCH ? "
                    "AND a.slug = ? AND d.relative_path = ? LIMIT 1",
                    (sanitize_fts_query(query), archive_slug, expected_path),
                ).fetchone()
                result = {
                    "archive_slug": archive_slug,
                    "query": query,
                    "expected_path": expected_path,
                    "status": "pass" if row else "fail",
                    "live_path": row[2] if row else None,
                    "archive_root": row[1] if row else None,
                }
                results.append(result)
                if row is None:
                    errors.append(
                        "project-specific memory query returned no exact archive/path hit: "
                        f"{archive_slug!r} {query!r} -> {expected_path!r}"
                    )
    except sqlite3.Error as exc:
        errors.append(f"memory read-only FTS check failed: {exc}")
    finally:
        if connection is not None:
            connection.close()
    if not any(result.get("status") == "pass" for result in results):
        errors.append("memory acceptance requires at least one live project-specific FTS hit")
    return errors, {
        "status": "pass" if not errors else "fail",
        "database": ".mir/memory.db",
        "mode": "immutable_read_only",
        "queries": results,
    }


def _validate_phase2(
    root: Path, surface: dict[str, object]
) -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    coverage = surface.get("coverage")
    if not isinstance(coverage, dict):
        errors.append("phase2_spec requires four-layer coverage")
        coverage = {}
    elif set(coverage) != set(_LAYER_KEYS):
        errors.append("phase2_spec coverage must contain exactly l1, l2, l3, and l4")
    for layer in _LAYER_KEYS:
        row = coverage.get(layer)
        if not isinstance(row, dict):
            errors.append(f"phase2_spec coverage is missing {layer}")
            continue
        values = {key: row.get(key) for key in _COUNT_KEYS}
        invalid_counts = any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in values.values()
        )
        if invalid_counts:
            errors.append(f"phase2_spec coverage {layer} counts must be non-negative integers")
            continue
        if values["total"] <= 0:
            errors.append(f"phase2_spec coverage {layer}.total must be greater than zero")
        if sum(values[key] for key in ("filled", "derived", "na", "tbd")) != values["total"]:
            errors.append(f"phase2_spec coverage {layer} counts do not sum to total")
        if values["tbd"] != 0:
            errors.append(f"phase2_spec coverage {layer} has unresolved TBD items")

    ai_ready = surface.get("ai_ready")
    if not isinstance(ai_ready, dict):
        errors.append("phase2_spec requires ai_ready counts")
        ai_ready = {}
    else:
        values = {key: ai_ready.get(key) for key in ("ready", "incomplete", "blocked")}
        invalid_counts = any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in values.values()
        )
        if invalid_counts:
            errors.append("phase2_spec ai_ready counts must be non-negative integers")
        elif values["ready"] <= 0 or values["incomplete"] != 0 or values["blocked"] != 0:
            errors.append(
                "phase2_spec ai_ready requires ready>0 and incomplete=blocked=0"
            )
    if surface.get("open_gaps") != 0:
        errors.append("phase2_spec open_gaps must equal zero")
    full_review = surface.get("full_review")
    if not isinstance(full_review, dict) or set(full_review) != set(_REVIEW_KEYS):
        errors.append("phase2_spec full_review must contain exactly five review keys")
    elif any(full_review.get(key) != "pass" for key in _REVIEW_KEYS):
        errors.append("phase2_spec full_review must pass every review key")

    native_evidence = surface.get("native_evidence")
    native_report: dict[str, object] = {"status": "fail"}
    if not isinstance(native_evidence, dict):
        errors.append("phase2_spec requires native_evidence field mappings")
    else:
        expected_native_keys = {
            "format",
            "meta_path",
            "coverage_key",
            "gaps_path",
            "review_path",
        }
        if set(native_evidence) != expected_native_keys:
            errors.append(
                "phase2_spec native_evidence must contain exactly format, meta_path, "
                "coverage_key, gaps_path, and review_path"
            )
        if native_evidence.get("format") != "mir_spec_yaml_v1":
            errors.append("phase2_spec native_evidence format must be mir_spec_yaml_v1")
        coverage_key = native_evidence.get("coverage_key")
        if coverage_key not in {"coverage", "completeness"}:
            errors.append(
                "phase2_spec native_evidence coverage_key must be coverage or completeness"
            )

        documents: dict[str, dict[str, object]] = {}
        normalized_paths: dict[str, str] = {}
        declared_paths = set(surface.get("evidence_paths", []))
        for field in ("meta_path", "gaps_path", "review_path"):
            try:
                path, normalized = _tracked_path(
                    root,
                    native_evidence.get(field),
                    label=f"phase2_spec native_evidence.{field}",
                )
            except AdoptionError as exc:
                errors.append(str(exc))
                continue
            normalized_paths[field] = normalized
            if normalized not in declared_paths:
                errors.append(
                    f"phase2_spec native evidence must be listed in evidence_paths: {normalized}"
                )
            try:
                document = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
                errors.append(f"phase2_spec native evidence is unreadable: {normalized}: {exc}")
                continue
            if not isinstance(document, dict):
                errors.append(
                    f"phase2_spec native evidence must contain a mapping: {normalized}"
                )
                continue
            documents[field] = document

        meta = documents.get("meta_path", {})
        native_coverage = meta.get(coverage_key) if isinstance(coverage_key, str) else None
        if not isinstance(native_coverage, dict):
            errors.append(
                f"phase2_spec native meta is missing mapped coverage key {coverage_key!r}"
            )
        else:
            for layer in _LAYER_KEYS:
                native_row = native_coverage.get(layer)
                manifest_row = coverage.get(layer) if isinstance(coverage, dict) else None
                if not isinstance(native_row, dict):
                    errors.append(f"phase2_spec native coverage is missing {layer}")
                    continue
                native_counts = {key: native_row.get(key) for key in _COUNT_KEYS}
                manifest_counts = (
                    {key: manifest_row.get(key) for key in _COUNT_KEYS}
                    if isinstance(manifest_row, dict)
                    else None
                )
                if native_counts != manifest_counts:
                    errors.append(
                        f"phase2_spec manifest coverage {layer} does not match native evidence"
                    )

        native_ai_ready = meta.get("ai_ready")
        if native_ai_ready != ai_ready:
            errors.append("phase2_spec manifest ai_ready does not match native evidence")

        gaps_document = documents.get("gaps_path", {})
        native_gaps = gaps_document.get("gaps")
        if not isinstance(native_gaps, list):
            errors.append("phase2_spec native gaps evidence must contain a gaps array")
        elif len(native_gaps) != surface.get("open_gaps"):
            errors.append("phase2_spec manifest open_gaps does not match native evidence")

        review_document = documents.get("review_path", {})
        native_reviews = review_document.get("reviews")
        review_statuses: dict[str, object] = {}
        review_evidence: dict[str, dict[str, object]] = {}
        if not isinstance(native_reviews, dict) or set(native_reviews) != set(_REVIEW_KEYS):
            errors.append(
                "phase2_spec native review evidence must contain exactly five review dimensions"
            )
        else:
            for dimension in _REVIEW_KEYS:
                row = native_reviews.get(dimension)
                if not isinstance(row, dict) or set(row) != {
                    "status",
                    "evidence_paths",
                    "verification",
                }:
                    errors.append(
                        "phase2_spec native review dimension must contain exactly status, "
                        f"evidence_paths, and verification: {dimension}"
                    )
                    continue
                review_statuses[dimension] = row.get("status")
                evidence_paths = row.get("evidence_paths")
                if (
                    not isinstance(evidence_paths, list)
                    or not evidence_paths
                    or len(set(map(str, evidence_paths))) != len(evidence_paths)
                ):
                    errors.append(
                        f"phase2_spec native review {dimension} requires unique evidence_paths"
                    )
                    evidence_paths = []
                verified_paths: list[str] = []
                for review_path in evidence_paths:
                    try:
                        _path, normalized = _tracked_path(
                            root,
                            review_path,
                            label=f"phase2_spec native review {dimension} evidence",
                        )
                    except AdoptionError as exc:
                        errors.append(str(exc))
                        continue
                    if normalized not in declared_paths:
                        errors.append(
                            "phase2_spec native review evidence must be listed in "
                            f"evidence_paths: {normalized}"
                        )
                    verified_paths.append(normalized)
                try:
                    verification = _non_placeholder_text(
                        row.get("verification"),
                        label=f"phase2_spec native review {dimension}.verification",
                    )
                except AdoptionError as exc:
                    errors.append(str(exc))
                    verification = ""
                review_evidence[dimension] = {
                    "status": row.get("status"),
                    "evidence_paths": verified_paths,
                    "verification": verification,
                }
        if review_statuses != full_review:
            errors.append("phase2_spec full_review does not match native review evidence")
        native_report = {
            "status": "pass" if not errors else "fail",
            "format": native_evidence.get("format"),
            "paths": normalized_paths,
            "reviews": review_evidence,
        }

    native_paths = set(native_report.get("paths", {}).values())
    for relative in surface.get("evidence_paths", []):
        path = root / str(relative)
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not body.strip():
            errors.append(f"phase2_spec evidence is empty: {relative}")
        elif relative not in native_paths and _contains_unresolved_placeholder(body):
            errors.append(f"phase2_spec evidence contains placeholder text: {relative}")
    return errors, {
        "status": "pass" if not errors else "fail",
        "coverage": coverage,
        "ai_ready": ai_ready,
        "open_gaps": surface.get("open_gaps"),
        "full_review": full_review,
        "native_evidence": native_report,
        "exceptions": [],
    }


def _evidence_digests(
    root: Path, surfaces: dict[str, dict[str, object]]
) -> list[dict[str, str]]:
    paths = sorted(
        {
            str(relative)
            for surface in surfaces.values()
            for relative in surface.get("evidence_paths", [])
        }
    )
    evidence: list[dict[str, str]] = []
    for relative in paths:
        path = root / relative
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        evidence.append({"path": relative, "sha256": digest})
    return evidence


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        os.close(descriptor)
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _emit(ns: argparse.Namespace, report: dict[str, object]) -> None:
    if ns.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return
    print(f"mir bootstrap-adoption: {report['status']}")
    for error in report.get("errors", []):
        print(f"  [not-ready] {error}")
    if report.get("receipt_written"):
        print("  receipt: .mir/bootstrap-receipt.json")


def main(argv: list[str] | None = None) -> int:
    # @spec CR-005 FR-002 FR-006 IR-002 QR-002
    ns = _parse(sys.argv[1:] if argv is None else argv)
    root = ns.project_root.expanduser().resolve()
    before = snapshot_project(root)
    manifest_path = root / "config/bootstrap-adoption.json"
    errors: list[str] = []
    try:
        manifest, manifest_bytes = _load_json_bytes(manifest_path)
    except AdoptionError as exc:
        report: dict[str, object] = {
            "schema_version": 1,
            "status": "not_ready",
            "apply": ns.apply,
            "receipt_written": False,
            "changed_paths": [],
            "errors": [str(exc)],
        }
        _emit(ns, report)
        return 2

    if manifest.get("schema_version") != 1:
        errors.append("config/bootstrap-adoption.json schema_version must be 1")
    allowed_manifest_keys = {
        "$schema",
        "schema_version",
        "project_slug",
        "repository_archetype",
        "profile",
        "mir_yoke_source_commit",
        "surfaces",
    }
    extra_manifest_keys = sorted(set(manifest) - allowed_manifest_keys)
    if extra_manifest_keys:
        errors.append(f"adoption manifest has unknown fields: {extra_manifest_keys}")
    commit = manifest.get("mir_yoke_source_commit")
    if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
        errors.append("mir_yoke_source_commit must be a lowercase 40-hex Git commit")
    profile_errors, profile = _validate_profile(root, manifest)
    errors.extend(profile_errors)
    surface_errors, surfaces, exceptions = _validate_surface_contract(root, manifest)
    errors.extend(surface_errors)

    gate: dict[str, object] = {"status": "not_checked"}
    launcher: dict[str, object] = {"status": "not_checked"}
    content: dict[str, object] = {"status": "not_checked"}
    memory: dict[str, object] = {"status": "not_checked", "queries": []}
    phase2: dict[str, object] = {"status": "not_checked", "exceptions": []}
    if surfaces:
        gate_surface = surfaces.get("bootstrap_start_gate", {})
        if gate_surface.get("disposition") in {"applied", "repository_owned"}:
            errors.extend(
                _validate_required_runtime_evidence(
                    gate_surface,
                    surface_name="bootstrap_start_gate",
                )
            )
            check_errors, gate = _validate_bootstrap_gate(root)
            errors.extend(check_errors)
            if gate_surface.get("disposition") == "applied":
                check_errors, canonical = _validate_canonical_applied_helper(
                    root,
                    ".claude/hooks/_lib/bootstrap-gate.sh",
                    label="bootstrap gate helper",
                )
                errors.extend(check_errors)
                gate["canonical"] = canonical

        launcher_surface = surfaces.get("managed_python_launcher", {})
        if launcher_surface.get("disposition") in {"applied", "repository_owned"}:
            errors.extend(
                _validate_required_runtime_evidence(
                    launcher_surface,
                    surface_name="managed_python_launcher",
                )
            )
            check_errors, launcher = _validate_python_launcher(root)
            errors.extend(check_errors)
            if launcher_surface.get("disposition") == "applied":
                check_errors, canonical = _validate_canonical_applied_helper(
                    root,
                    ".claude/hooks/_lib/run-python.sh",
                    label="managed Python launcher",
                )
                errors.extend(check_errors)
                launcher["canonical"] = canonical

        content_surface = surfaces.get("content_onboarding", {})
        content_disposition = content_surface.get("disposition")
        selected_profile = manifest.get("profile")
        if selected_profile == "content_workspace" and content_disposition == "not_applicable":
            errors.append("content_workspace cannot mark content_onboarding not_applicable")
        elif content_disposition in {"applied", "repository_owned"}:
            check_errors, content = _validate_content_onboarding(root, selected_profile)
            errors.extend(check_errors)
        elif content_disposition == "not_applicable":
            content = {
                "status": "not_applicable",
                "reason": content_surface.get("reason"),
            }
        elif content_disposition == "exception":
            content = {"status": "exception", "reason": content_surface.get("reason")}

        memory_surface = surfaces.get("memory_acceptance", {})
        if memory_surface.get("disposition") in {"applied", "repository_owned"}:
            check_errors, memory = _validate_memory(root, memory_surface)
            errors.extend(check_errors)
        elif memory_surface.get("disposition") == "exception":
            memory = {
                "status": "exception",
                "queries": [],
                "reason": memory_surface.get("reason"),
            }

        phase_surface = surfaces.get("phase2_spec", {})
        if phase_surface.get("disposition") in {"applied", "repository_owned"}:
            check_errors, phase2 = _validate_phase2(root, phase_surface)
            errors.extend(check_errors)
        elif phase_surface.get("disposition") == "exception":
            phase_exception = next(
                (item for item in exceptions if item["surface"] == "phase2_spec"),
                None,
            )
            phase2 = {
                "status": "exception",
                "exceptions": [phase_exception] if phase_exception else [],
            }

    status = "ready" if not errors else "not_ready"
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    receipt: dict[str, object] = {
        "schema_version": 1,
        "status": status,
        "mode": "existing_repository_adoption",
        "project": {
            "slug": manifest.get("project_slug"),
            "repository_archetype": manifest.get("repository_archetype"),
            "profile": manifest.get("profile"),
        },
        "source": {"mir_yoke_commit": commit},
        "manifest": {
            "path": "config/bootstrap-adoption.json",
            "sha256": manifest_hash,
        },
        "evidence": _evidence_digests(root, surfaces),
        "profile": profile,
        "surfaces": surfaces,
        "bootstrap_start_gate": gate,
        "managed_python_launcher": launcher,
        "content_onboarding": content,
        "memory_acceptance": memory,
        "phase2": phase2,
        "exceptions": exceptions,
        "errors": errors,
    }
    receipt_written = False
    if ns.apply and status == "ready":
        _atomic_write_json(root / ".mir/bootstrap-receipt.json", receipt)
        receipt_written = True

    report = dict(receipt)
    report["apply"] = ns.apply
    report["receipt_written"] = receipt_written
    report["changed_paths"] = changed_paths(before, snapshot_project(root))
    report["reference_assets"] = [
        {
            "asset": name,
            "disposition": surface.get("disposition"),
            "evidence_paths": surface.get("evidence_paths", []),
        }
        for name, surface in sorted(surfaces.items())
    ]
    _emit(ns, report)
    return 0 if status == "ready" else 2
