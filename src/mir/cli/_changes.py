"""Repository-local changed-path evidence for explicit consumer operations."""

from __future__ import annotations

import hashlib
from pathlib import Path

_EXCLUDED_DIRS = frozenset({".git", ".pytest_cache", ".venv", "__pycache__"})


def snapshot_project(root: Path) -> dict[str, str]:
    """Return content identities for files inside one declared repository root."""
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in _EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.is_symlink():
            snapshot[relative.as_posix()] = f"symlink:{path.readlink()}"
        elif path.is_file():
            snapshot[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


# @spec IR-002
def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )
