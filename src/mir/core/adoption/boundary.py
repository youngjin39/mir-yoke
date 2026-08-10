"""Shared product/provider boundary classification."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path, PurePosixPath

import jsonschema

BOUNDARY_PATH = Path("config/adopter-boundary.json")
PROFILE_PATH = Path(".mir/repo-profile.toml")


class BoundaryError(ValueError):
    """The adopter boundary cannot be classified safely."""


def _safe_relative(raw: object) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise BoundaryError(f"invalid adopter boundary path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise BoundaryError(f"unsafe adopter boundary path: {raw!r}")
    return path.as_posix()


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoundaryError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise BoundaryError(f"{path} must be a schema_version=1 object")
    schema_ref = payload.get("$schema")
    if isinstance(schema_ref, str):
        schema_path = path.parent / schema_ref
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(payload, schema)
        except (OSError, json.JSONDecodeError, jsonschema.ValidationError) as exc:
            raise BoundaryError(f"invalid {path}: {exc}") from exc
    return payload


def load_boundary(project_root: Path) -> dict[str, object]:
    boundary = _load_json(project_root / BOUNDARY_PATH)
    for key in ("provider_markers",):
        values = boundary.get(key)
        if not isinstance(values, list) or not values:
            raise BoundaryError(f"{BOUNDARY_PATH} requires non-empty {key}")
        boundary[key] = [_safe_relative(value) for value in values]
    text_markers = boundary.get("provider_text_markers")
    if not isinstance(text_markers, list):
        raise BoundaryError(f"{BOUNDARY_PATH} requires provider_text_markers")
    for marker in text_markers:
        if not isinstance(marker, dict):
            raise BoundaryError("provider_text_markers entries must be objects")
        marker["path"] = _safe_relative(marker.get("path"))
        if not isinstance(marker.get("contains"), str) or not marker["contains"]:
            raise BoundaryError("provider text markers require non-empty contains")
    return boundary


def load_profile(project_root: Path) -> dict[str, object]:
    profile_path = project_root / PROFILE_PATH
    try:
        with profile_path.open("rb") as handle:
            profile = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise BoundaryError(
            f"cannot classify adopter payload without a readable Profile: {exc}"
        ) from exc
    repo = profile.get("repo")
    if not isinstance(repo, dict):
        raise BoundaryError("cannot classify adopter payload because Profile [repo] is missing")
    return profile


def is_provider_owner(profile: dict[str, object], boundary: dict[str, object]) -> bool:
    repo = profile["repo"]
    assert isinstance(repo, dict)
    slug = repo.get("slug")
    repository_type = repo.get("repository_type")
    owners = boundary.get("provider_owners")
    if not isinstance(owners, list):
        raise BoundaryError(f"{BOUNDARY_PATH} requires provider_owners")
    return any(
        isinstance(owner, dict)
        and slug == owner.get("slug")
        and isinstance(owner.get("repository_types"), list)
        and repository_type in owner["repository_types"]
        for owner in owners
    )


def payload_findings(
    project_root: Path,
    *,
    boundary: dict[str, object] | None = None,
    profile: dict[str, object] | None = None,
) -> list[dict[str, str]]:
    boundary = boundary or load_boundary(project_root)
    profile = profile or load_profile(project_root)
    if is_provider_owner(profile, boundary):
        return []

    findings: list[dict[str, str]] = []
    for relative in boundary["provider_markers"]:
        target = project_root / str(relative)
        if target.exists() or target.is_symlink():
            findings.append({"kind": "path", "path": str(relative)})
    for marker in boundary["provider_text_markers"]:
        assert isinstance(marker, dict)
        relative = str(marker["path"])
        target = project_root / relative
        try:
            text = target.read_text(encoding="utf-8")
        except OSError:
            continue
        if str(marker["contains"]) in text:
            findings.append({"kind": "text", "path": relative})
    return findings
