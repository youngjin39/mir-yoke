"""Repository-local catalog loader.

Reads config/repo-agent-management.json and config/repos/<slug>.json
into a single aggregated dict compatible with the v3.5 single-file
shape. Used by repository-local verifiers and tests.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_catalog(repo_root: Path) -> dict[str, Any]:
    """Load aggregated catalog with repositories[] inlined from
    config/repos/*.json when repositories_dir is set.

    Returns the same shape as the v3.5 single-file catalog so
    downstream code is unchanged.
    """
    root_path = repo_root / "config" / "repo-agent-management.json"
    data = json.loads(root_path.read_text(encoding="utf-8"))

    if "repositories" not in data and "repositories_dir" in data:
        repos_dir = repo_root / data["repositories_dir"]
        repos = []
        if repos_dir.is_dir():
            for repo_file in sorted(repos_dir.glob("*.json")):
                # Skip schema reference files etc.
                if repo_file.name.startswith("_"):
                    continue
                entry = json.loads(repo_file.read_text(encoding="utf-8"))
                # Strip $schema if present (loader-only metadata)
                entry.pop("$schema", None)
                repos.append(entry)
        data["repositories"] = repos

    return data
