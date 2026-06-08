"""SkillRegistry — `mir.skills` entry_points.

design §8.4. Phase 1 uses an empty Registry (Mir built-in skills stay in .claude/skills/).
Structure that lets family-specific skills be registered as entry_points.
"""
from __future__ import annotations

from .base import EntryPointRegistry


class SkillRegistry(EntryPointRegistry):
    GROUP = "mir.skills"
