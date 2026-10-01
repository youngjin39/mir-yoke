"""Yoke-owned application validation; excluded from common executor delivery."""
from __future__ import annotations

import pathlib


def validate_brief(brief: pathlib.Path | str, repo_root: pathlib.Path):
    """Preserve Yoke's typed file schema while accepting ordinary text prompts."""
    if isinstance(brief, pathlib.Path):
        from mir.core.conductor.dispatch_brief import load_dispatch_brief

        return load_dispatch_brief(brief)
    return None
