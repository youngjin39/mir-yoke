"""Preservation-first repository planning and explicit transactional apply."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from .catalog import (
    DistributionError,
    atomic_write_json,
    content_digest,
    load_pack_manifests,
    load_profile,
    provider_files,
    safe_relative_path,
    sha256_file,
    source_revision,
)
from .catalog import install_provider as install_provider


class CompositionError(DistributionError):
    """A plan would violate target ownership or transactional safety."""


def _plan_id(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _selected_packs(
    manifests: dict[str, dict[str, object]],
    requested: list[str],
) -> list[str]:
    selected: list[str] = []
    visiting: set[str] = set()

    def include(pack_id: str) -> None:
        if pack_id in selected:
            return
        if pack_id in visiting:
            raise CompositionError(f"pack dependency cycle: {pack_id}")
        try:
            pack = manifests[pack_id]
        except KeyError as exc:
            raise CompositionError(f"unknown capability pack: {pack_id}") from exc
        visiting.add(pack_id)
        dependencies = pack.get("dependencies")
        if not isinstance(dependencies, list):
            raise CompositionError(f"pack dependencies are invalid: {pack_id}")
        for dependency in dependencies:
            if not isinstance(dependency, str):
                raise CompositionError(f"pack dependency is invalid: {pack_id}")
            include(dependency)
        visiting.remove(pack_id)
        selected.append(pack_id)

    for requested_id in requested:
        include(requested_id)
    return selected


def _target_path(root: Path, relative: str) -> Path:
    safe = safe_relative_path(relative)
    target = root / safe
    current = target.parent
    while current != root:
        if current.is_symlink():
            raise CompositionError(f"target parent is a symlink: {relative}")
        current = current.parent
    try:
        target.parent.resolve().relative_to(root)
    except ValueError as exc:
        raise CompositionError(f"target escapes repository: {relative}") from exc
    return target


def _source_asset(root: Path, relative: str) -> Path:
    safe = safe_relative_path(relative)
    source = root / safe
    if source.is_symlink() or not source.is_file():
        raise CompositionError(f"source asset is missing or linked: {relative}")
    try:
        source.resolve().relative_to(root)
    except ValueError as exc:
        raise CompositionError(f"source asset escapes provider: {relative}") from exc
    return source


def create_plan(
    source_root: Path,
    target_root: Path,
    *,
    profile: str = "minimal",
    packs: tuple[str, ...] = (),
    include_recommended: bool = False,
    include_core: bool = True,
) -> dict[str, object]:
    source_root = source_root.resolve()
    target_root = target_root.resolve()
    if source_root == target_root or source_root in target_root.parents:
        raise CompositionError("target repository must be outside the provider source")
    if not target_root.is_dir() or target_root.is_symlink():
        raise CompositionError(f"target root is not a real directory: {target_root}")
    manifests = load_pack_manifests(source_root)
    profile_payload = load_profile(source_root, profile)
    composition = profile_payload["composition"]
    assert isinstance(composition, dict)
    requested = [*composition["default_packs"], *packs]
    if include_recommended:
        requested.extend(composition["recommended_packs"])
    selected = _selected_packs(manifests, list(dict.fromkeys(requested)))

    assets: dict[str, str] = {}
    if include_core:
        for source in sorted((source_root / "starter").iterdir()):
            if source.is_file():
                assets[source.name] = source.relative_to(source_root).as_posix()
    for pack_id in selected:
        adoption_assets = manifests[pack_id].get("adoption_assets")
        if not isinstance(adoption_assets, list):
            raise CompositionError(f"pack adoption assets are invalid: {pack_id}")
        for asset in adoption_assets:
            if not isinstance(asset, dict):
                raise CompositionError(f"pack adoption asset is invalid: {pack_id}")
            source = asset.get("source")
            target = asset.get("target")
            if not isinstance(source, str) or not isinstance(target, str):
                raise CompositionError(f"pack adoption mapping is invalid: {pack_id}")
            existing = assets.get(target)
            existing_hash = (
                sha256_file(_source_asset(source_root, existing))
                if existing is not None
                else None
            )
            if existing_hash is not None and existing_hash != sha256_file(
                _source_asset(source_root, source)
            ):
                raise CompositionError(f"multiple assets target different content: {target}")
            assets[target] = source

    files: list[dict[str, object]] = []
    for target_relative, source_relative in sorted(assets.items()):
        source = _source_asset(source_root, source_relative)
        target = _target_path(target_root, target_relative)
        source_hash = sha256_file(source)
        row: dict[str, object] = {
            "source": source_relative,
            "target": safe_relative_path(target_relative),
            "sha256": source_hash,
        }
        if target.is_symlink() or (target.exists() and not target.is_file()):
            row["action"] = "conflict"
            row["target_type"] = "unsafe"
        elif not target.exists():
            row["action"] = "create"
        else:
            target_hash = sha256_file(target)
            row["target_sha256"] = target_hash
            row["action"] = "identical" if target_hash == source_hash else "conflict"
        files.append(row)

    provider = provider_files(source_root)
    payload: dict[str, object] = {
        "schema_version": 1,
        "profile": profile,
        "packs": selected,
        "provider": {
            "content_digest": content_digest(provider),
            "source_revision": source_revision(source_root),
        },
        "files": files,
    }
    payload["plan_id"] = _plan_id(payload)
    return payload


def _restore_bytes(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(previous)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def apply_plan(
    source_root: Path,
    target_root: Path,
    plan: dict[str, object],
) -> dict[str, object]:
    source_root = source_root.resolve()
    target_root = target_root.resolve()
    plan_id = plan.get("plan_id")
    files = plan.get("files")
    provider = plan.get("provider")
    if not (
        isinstance(plan_id, str)
        and isinstance(files, list)
        and isinstance(provider, dict)
    ):
        raise CompositionError("composition plan is invalid")
    canonical = dict(plan)
    canonical.pop("plan_id", None)
    if _plan_id(canonical) != plan_id:
        raise CompositionError("composition plan digest mismatch")
    current_digest = content_digest(provider_files(source_root))
    if provider.get("content_digest") != current_digest:
        raise CompositionError("provider source changed after planning")
    conflicts = [
        row.get("target")
        for row in files
        if isinstance(row, dict) and row.get("action") == "conflict"
    ]
    if conflicts:
        rendered = ", ".join(map(str, conflicts))
        raise CompositionError(f"composition plan contains conflicts: {rendered}")

    create_rows: list[tuple[dict[str, object], Path, Path]] = []
    for row in files:
        if not isinstance(row, dict):
            raise CompositionError("composition file entry is invalid")
        source_relative = row.get("source")
        target_relative = row.get("target")
        expected = row.get("sha256")
        action = row.get("action")
        required = (source_relative, target_relative, expected, action)
        if not all(isinstance(item, str) for item in required):
            raise CompositionError("composition file entry is incomplete")
        source = _source_asset(source_root, source_relative)
        target = _target_path(target_root, target_relative)
        if sha256_file(source) != expected:
            raise CompositionError(f"source changed after planning: {source_relative}")
        if action == "create":
            if target.exists() or target.is_symlink():
                raise CompositionError(f"target changed after planning: {target_relative}")
            create_rows.append((row, source, target))
        elif action == "identical":
            if not target.is_file() or target.is_symlink() or sha256_file(target) != expected:
                raise CompositionError(f"target changed after planning: {target_relative}")
        else:
            raise CompositionError(f"unsupported composition action: {action}")

    local_state = target_root / ".mir/local-state.json"
    receipt = target_root / ".mir/yoke-receipts" / f"{plan_id}.json"
    prior_state = local_state.read_bytes() if local_state.is_file() else None
    prior_receipt = receipt.read_bytes() if receipt.is_file() else None
    stage = Path(tempfile.mkdtemp(prefix=".yoke-stage-", dir=target_root))
    created: list[Path] = []
    created_parents: set[Path] = set()
    try:
        staged_files: list[tuple[Path, Path]] = []
        for row, source, target in create_rows:
            staged = stage / str(row["target"])
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged)
            if sha256_file(staged) != row["sha256"]:
                raise CompositionError(f"staged asset digest mismatch: {row['target']}")
            staged_files.append((staged, target))
        for staged, target in staged_files:
            target.parent.mkdir(parents=True, exist_ok=True)
            created_parents.add(target.parent)
            os.replace(staged, target)
            created.append(target)
        receipt_payload: dict[str, object] = {
            "schema_version": 1,
            "status": "applied",
            "plan_id": plan_id,
            "profile": plan.get("profile"),
            "packs": plan.get("packs"),
            "provider": provider,
            "created": [path.relative_to(target_root).as_posix() for path in created],
        }
        atomic_write_json(receipt, receipt_payload)
        atomic_write_json(
            local_state,
            {
                "schema_version": 1,
                "provider": provider,
                "profile": plan.get("profile"),
                "packs": plan.get("packs"),
                "last_plan_id": plan_id,
            },
        )
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        _restore_bytes(receipt, prior_receipt)
        _restore_bytes(local_state, prior_state)
        for directory in sorted(created_parents, key=lambda item: len(item.parts), reverse=True):
            current = directory
            while current != target_root:
                try:
                    current.rmdir()
                except OSError:
                    break
                current = current.parent
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return {
        "status": "applied",
        "plan_id": plan_id,
        "created": [path.relative_to(target_root).as_posix() for path in created],
        "receipt": receipt.relative_to(target_root).as_posix(),
    }


def write_plan(path: Path, plan: dict[str, object]) -> None:
    atomic_write_json(path, plan)
