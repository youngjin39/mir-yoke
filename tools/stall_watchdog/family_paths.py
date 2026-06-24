"""Workspace-encoded directory to family slug reverse map.

ADR-06 §2.2.1 - single-pool JSONL model. ``~/.claude-agents/{family}/.claude/projects``
is a symlink to ``<your-home>/.claude/projects`` for every family (verified
2026-05-11). Workspace identity is encoded in the JSONL directory name with
Claude Code path-encoding (``/``, ``.``, ``_``, space all become ``-``).

WORKSPACE_DIR_TO_FAMILY maps the encoded directory name to the ASCII family
slug used throughout the your-harness profile system (e.g. ``<example-family>``, ``your-harness``).
This dict must stay byte-aligned with the user-confirmed family path table in
the ``reference_family_paths`` auto-memory entry. Legacy / pre-migration
workspace directories are mapped to the same family slug they previously
belonged to so historical sessions still resolve.

Korean display names live in FAMILY_SLUG_TO_DISPLAY (Unicode escapes for
byte-stable storage across heredocs and editors).
"""

from __future__ import annotations

WORKSPACE_DIR_TO_FAMILY: dict[str, str] = {
    "-Volumes-T7-Shield-Project-01-Flutter-01-<example-family>": "<example-family>",
    "-Volumes-T7-Shield-Project-01-Flutter-02-GrowNote": "<example-family>",
    "-Volumes-T7-Shield-Project-01-Flutter-03-MineSweeper": "minesweeper",
    "-Volumes-T7-Shield-Project-03-StoryDirector": "story-director",
    "-Volumes-T7-Shield-Project-04-MY-Life": "<example-family>",
    "-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>",
    "-Volumes-T7-Shield-Project-06-StockDirector": "stock-director",
    "-Volumes-T7-Shield-Project-07-ShortMovieDirector": "short-movie-director",
    "-Volumes-T7-Shield-Project-09-Mini-Harness": "your-harness",
    "-Volumes-T7-Shield-Project-11-Musinsa-Brand": "<example-family>",
    "-Volumes-T7-Shield-Project-12-Memory-Keeper": "memory-keeper",
    "-Users-ai-agent-home-server": "home-server",
    "-Users-ai-agent-Hermes": "<example-family>",
    "-Users-ai-agent-Flutter-Project-MineSweeper": "minesweeper",
    "-Users-ai-agent-Flutter-Project-GrowNote": "<example-family>",
    "-Users-ai-agent-Flutter-Project-DEVELOPMENT-GUIDE-<example-family>": "<example-family>",
}

FAMILY_SLUG_TO_DISPLAY: dict[str, str] = {
    "<example-family-1>": "<example-family>",
    "<example-family-2>": "<example-family>",
    "minesweeper": "<example-family>",
    "story-director": "<example-family>",
    "<example-family-3>": "<example-family>",
    "<example-family-4>": "<example-family>",
    "stock-director": "<example-family>",
    "short-movie-director": "<example-family>",
    "your-harness": "your harness",
    "home-server": "<example-family>",
    "<example-family-5>": "<example-family>",
    "<example-family-6>": "<example-family>",
    "memory-keeper": "<example-family>",
}


def family_slug_to_env_key(family_slug: str) -> str:
    """Return the ASCII env-var suffix used for per-family secrets.

    The your-harness profile family slug (hyphen-snake) is normalized to upper snake-case
    for use in ``MIR_STALL_WATCHDOG_WEBHOOK_<SUFFIX>``. Unknown slug returns
    ``"UNKNOWN"`` (callers should fall back to the DEFAULT webhook).
    """
    if family_slug not in FAMILY_SLUG_TO_DISPLAY:
        return "UNKNOWN"
    return family_slug.upper().replace("-", "_")


def family_display_name(family_slug: str) -> str:
    """Return the Korean display name for a family slug, or the slug itself."""
    return FAMILY_SLUG_TO_DISPLAY.get(family_slug, family_slug)
