"""Deterministic attestation for an installed, project-isolated Mir CLI runtime."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

_TRANSIENT_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache"}
_TRANSIENT_SUFFIXES = {".pyc", ".pyo"}


def _is_transient(relative: Path) -> bool:
    return bool(_TRANSIENT_DIRS.intersection(relative.parts)) or (
        relative.suffix in _TRANSIENT_SUFFIXES
    )


def _entry(path: Path, relative: Path) -> dict[str, object]:
    metadata = path.lstat()
    base: dict[str, object] = {
        "path": relative.as_posix(),
        "mode": stat.S_IMODE(metadata.st_mode),
    }
    if path.is_symlink():
        return {**base, "type": "symlink", "target": os.readlink(path)}
    return {
        **base,
        "type": "file",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _runtime_entries(runtime_root: Path, manifest: Path) -> list[dict[str, object]]:
    root = runtime_root.resolve(strict=True)
    excluded = manifest.resolve(strict=False)
    entries: list[dict[str, object]] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        retained_directories: list[str] = []
        for name in sorted(directories):
            path = current_path / name
            relative = path.relative_to(root)
            if _is_transient(relative):
                continue
            if path.is_symlink():
                entries.append(_entry(path, relative))
            else:
                retained_directories.append(name)
        directories[:] = retained_directories
        for name in sorted(files):
            path = current_path / name
            relative = path.relative_to(root)
            if _is_transient(relative) or path.absolute() == excluded:
                continue
            entries.append(_entry(path, relative))
    return sorted(entries, key=lambda item: str(item["path"]))


def create_runtime_manifest(
    runtime_root: Path,
    manifest: Path,
    *,
    source_url: str,
    source_commit: str,
    constraints_sha256: str,
) -> dict[str, object]:
    """Write an atomic manifest that binds the installed runtime closure."""
    root = runtime_root.expanduser().resolve(strict=True)
    target = manifest.expanduser().resolve(strict=False)
    if target.parent != root:
        raise ValueError("runtime manifest must be a direct child of the runtime root")
    document: dict[str, object] = {
        "schema_version": 1,
        "source_url": source_url,
        "source_commit": source_commit,
        "constraints_sha256": constraints_sha256,
        "entries": _runtime_entries(root, target),
    }
    body = json.dumps(document, indent=2, sort_keys=True) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return document


def verify_runtime_manifest(
    runtime_root: Path,
    manifest: Path,
    *,
    source_url: str | None = None,
    source_commit: str | None = None,
    constraints_sha256: str | None = None,
) -> list[str]:
    """Return fail-closed findings for a runtime manifest and installed closure."""
    try:
        root = runtime_root.expanduser().resolve(strict=True)
        target = manifest.expanduser().resolve(strict=True)
        if target.parent != root or target.is_symlink():
            return ["runtime manifest is outside the runtime root"]
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["runtime manifest is unreadable"]
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        return ["runtime manifest schema is invalid"]
    expected_metadata = {
        "source_url": source_url,
        "source_commit": source_commit,
        "constraints_sha256": constraints_sha256,
    }
    if any(
        expected is not None and document.get(name) != expected
        for name, expected in expected_metadata.items()
    ):
        return ["runtime manifest source evidence differs"]
    expected = document.get("entries")
    if not isinstance(expected, list):
        return ["runtime manifest entries are invalid"]
    try:
        actual = _runtime_entries(root, target)
    except OSError:
        return ["runtime closure is unreadable"]
    if actual != expected:
        return ["runtime closure differs from manifest"]
    return []
