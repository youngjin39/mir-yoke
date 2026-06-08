"""AgentRegistry — `mir.agents` entry_points (AgentProfile instance factory).

design §8.4. Each entry_point is an `AgentProfile` instance or factory function.
"""
from __future__ import annotations

from .base import EntryPointRegistry


class AgentRegistry(EntryPointRegistry):
    GROUP = "mir.agents"
