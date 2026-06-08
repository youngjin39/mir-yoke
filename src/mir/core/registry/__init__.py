"""Mir Registry quartet — entry_points-based extension points.

design §8.4 · V9 · H9.
Hardcoding prohibition: no class literal dicts inside this package.
Additions are one line in `pyproject.toml [project.entry-points."mir.<group>"]`.
"""
from .agents import AgentRegistry
from .base import EntryPointRegistry
from .embedding_backends import EmbeddingBackendRegistry
from .providers import ProviderRegistry
from .skills import SkillRegistry

__all__ = [
    "AgentRegistry",
    "EmbeddingBackendRegistry",
    "EntryPointRegistry",
    "ProviderRegistry",
    "SkillRegistry",
]
