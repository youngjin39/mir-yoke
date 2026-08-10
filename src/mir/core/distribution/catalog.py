"""Validated access to product planes, profiles, packs, and provider sources."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path, PurePosixPath

import jsonschema

_PROVIDER_STATIC_FILES = (
    "VERSION",
    "LICENSE",
    "config/product-planes.json",
    "config/product-planes.schema.json",
    "config/capability-pack.schema.json",
)


class DistributionError(ValueError):
    """The requested distribution or composition source is invalid."""


def safe_relative_path(raw: str) -> str:
    if not raw or "\\" in raw:
        raise DistributionError(f"unsafe relative path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise DistributionError(f"unsafe relative path: {raw!r}")
    return path.as_posix()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise DistributionError(f"source file is missing or linked: {path}")
    return sha256_bytes(path.read_bytes())


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def load_product_planes(root: Path) -> dict[str, object]:
    path = root / "config/product-planes.json"
    schema_path = root / "config/product-planes.schema.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(payload, schema)
    except (OSError, json.JSONDecodeError, jsonschema.ValidationError) as exc:
        raise DistributionError(f"invalid product plane manifest: {exc}") from exc
    return payload


def load_pack_manifests(root: Path) -> dict[str, dict[str, object]]:
    schema_path = root / "config/capability-pack.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DistributionError(f"invalid capability pack schema: {exc}") from exc
    packs: dict[str, dict[str, object]] = {}
    for path in sorted((root / "packs").glob("*/pack.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            jsonschema.validate(payload, schema)
        except (OSError, json.JSONDecodeError, jsonschema.ValidationError) as exc:
            raise DistributionError(f"invalid pack manifest {path}: {exc}") from exc
        pack_id = payload.get("id")
        if not isinstance(pack_id, str) or path.parent.name != pack_id:
            raise DistributionError(f"pack id/path mismatch: {path}")
        if pack_id in packs:
            raise DistributionError(f"duplicate pack id: {pack_id}")
        packs[pack_id] = payload
    known = set(packs)
    for pack_id, payload in packs.items():
        dependencies = payload.get("dependencies")
        if not isinstance(dependencies, list) or not set(dependencies) <= known:
            raise DistributionError(f"pack {pack_id} references an unknown dependency")
    return packs


def load_profile(root: Path, name: str) -> dict[str, object]:
    safe_name = safe_relative_path(name)
    if "/" in safe_name:
        raise DistributionError(f"invalid profile name: {name!r}")
    path = root / "profiles" / f"{safe_name}.toml"
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise DistributionError(f"invalid profile {name!r}: {exc}") from exc
    if payload.get("schema_version") != 1 or payload.get("name") != name:
        raise DistributionError(f"profile identity mismatch: {name!r}")
    composition = payload.get("composition")
    policy = payload.get("policy")
    if not isinstance(composition, dict) or not isinstance(policy, dict):
        raise DistributionError(f"profile sections are missing: {name!r}")
    for field in ("default_packs", "recommended_packs"):
        value = composition.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise DistributionError(f"profile {name!r} has invalid {field}")
    if policy.get("mandatory") is not False:
        raise DistributionError(f"profile {name!r} must remain advisory")
    return payload


def expand_source_paths(root: Path, patterns: list[str]) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for pattern in patterns:
        safe_relative_path(pattern)
        matches = sorted(path for path in root.glob(pattern) if path.is_file())
        if not matches:
            raise DistributionError(f"source pattern matched no files: {pattern}")
        for path in matches:
            if path.is_symlink():
                raise DistributionError(f"source pattern resolved to a symlink: {path}")
            relative = path.relative_to(root).as_posix()
            files[relative] = path
    return files


def provider_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for relative in _PROVIDER_STATIC_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise DistributionError(f"provider source is missing: {relative}")
        files[relative] = path
    for directory in ("starter", "packs", "profiles"):
        for path in sorted((root / directory).rglob("*")):
            if path.is_symlink():
                raise DistributionError(f"provider source contains a symlink: {path}")
            if path.is_file():
                files[path.relative_to(root).as_posix()] = path
    for pack in load_pack_manifests(root).values():
        patterns = pack.get("source_paths")
        if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
            raise DistributionError("pack source paths are invalid")
        files.update(expand_source_paths(root, patterns))
    return files


def content_digest(files: dict[str, Path]) -> str:
    digest = hashlib.sha256()
    for relative, path in sorted(files.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def source_revision(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    revision = completed.stdout.strip()
    return revision if completed.returncode == 0 and revision else "unversioned"


def source_is_clean(root: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0 and not completed.stdout.strip()


def install_provider(source_root: Path, provider_home: Path) -> Path:
    source_root = source_root.resolve()
    provider_home = provider_home.expanduser().resolve()
    files = provider_files(source_root)
    digest = content_digest(files)
    providers = provider_home / "providers"
    target = providers / digest
    if target.is_dir() and not target.is_symlink():
        receipt_path = target / "provider.json"
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DistributionError(f"installed provider receipt is invalid: {target}") from exc
        if receipt.get("content_digest") != digest:
            raise DistributionError(f"installed provider digest mismatch: {target}")
        return target
    if target.exists() or target.is_symlink():
        raise DistributionError(f"provider target is unsafe: {target}")

    providers.mkdir(parents=True, exist_ok=True)
    raw_stage = Path(tempfile.mkdtemp(prefix=".provider-", dir=providers))
    try:
        for relative, source in sorted(files.items()):
            destination = raw_stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        atomic_write_json(
            raw_stage / "provider.json",
            {
                "schema_version": 1,
                "content_digest": digest,
                "source_revision": source_revision(source_root),
                "version": (source_root / "VERSION").read_text(encoding="utf-8").strip(),
            },
        )
        os.replace(raw_stage, target)
    finally:
        if raw_stage.exists():
            shutil.rmtree(raw_stage)
    return target
