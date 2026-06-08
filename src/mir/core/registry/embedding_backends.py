"""EmbeddingBackendRegistry — `mir.embedding_backends` entry_points.

design §5.2 · §8.4 (V9). Phase 1 default implementation = OmlxHttpBackend (implemented in Step 2).
"""
from __future__ import annotations

from .base import EntryPointRegistry


class EmbeddingBackendRegistry(EntryPointRegistry):
    GROUP = "mir.embedding_backends"
