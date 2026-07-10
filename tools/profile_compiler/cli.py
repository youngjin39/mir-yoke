"""
tools.profile_compiler.cli
--------------------------
Minimal profile compiler CLI stub for the Claude+Codex Harness Template.

The full profile compiler (cli.py with render/, bootstrap.py, etc.) is
fleet-private. This stub provides the minimum surface the public template
verifier (scripts/verify_repo_agent_management.py) needs:

  - _FAMILY_PATHS: empty by default — populate when you fork this template
                   and register your own family repositories.

To add a family, add an entry to _FAMILY_PATHS:
  _FAMILY_PATHS["my-repo"] = pathlib.Path("/absolute/path/to/my-repo")

To use the full profile compiler (generating role-policy blocks, hooks, etc.)
you need the private fleet tooling. This stub is sufficient for:
  - config/repo-agent-management.json validation
  - agent frontmatter validation (via tools/agent_loader)
  - the harness template verifier
"""

from __future__ import annotations

import pathlib
import sys

# ---------------------------------------------------------------------------
# Family path registry -- populate when you fork and register family repos
# ---------------------------------------------------------------------------
# Keys are the canonical normalized slug (lowercase, hyphens).
# Values are absolute paths to the family repository root.
#
# Example:
#   _FAMILY_PATHS: dict[str, pathlib.Path] = {
#       "my-project": pathlib.Path("/path/to/my-project"),
#       "another-repo": pathlib.Path("/path/to/another-repo"),
#   }
_FAMILY_PATHS: dict[str, pathlib.Path] = {}


def _normalize_slug(slug: str) -> str:
    return slug.lower().replace("_", "-")


def resolve_family_path(slug: str) -> pathlib.Path:
    normalized = _normalize_slug(slug)
    if normalized not in _FAMILY_PATHS:
        known = ", ".join(sorted(_FAMILY_PATHS)) or "(none registered)"
        raise KeyError(f"Unknown family slug: {slug!r} (normalized: {normalized!r}).\nKnown slugs: {known}")
    return _FAMILY_PATHS[normalized]


def main() -> None:
    """Entry point placeholder. Extend when adding full profile compiler support."""
    print(
        "mir-yoke profile compiler stub.\n"
        "To use the full profile compiler, extend this module with your fleet's\n"
        "render/, bootstrap.py, and profile_loader.py from the harness design.",
        file=sys.stderr,
    )
    sys.exit(0)
