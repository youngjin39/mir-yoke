"""EntryPointRegistry — common base · based on Python `importlib.metadata.entry_points`.

design §8.4. Subclasses specify only the `GROUP` class variable.
"""
from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any


class EntryPointRegistry:
    """Provide only name→class mappings after loading entry_points. No hardcoded dicts."""

    GROUP: str = ""  # set by subclasses

    def __init__(self) -> None:
        if not self.GROUP:
            raise NotImplementedError(
                f"{type(self).__name__} must set `GROUP` class variable"
            )
        self._cache: dict[str, type[Any]] | None = None

    def _discover(self) -> dict[str, type[Any]]:
        if self._cache is None:
            self._cache = {ep.name: ep.load() for ep in entry_points(group=self.GROUP)}
        return self._cache

    def get(self, name: str) -> type[Any]:
        eps = self._discover()
        if name not in eps:
            raise KeyError(f"{self.GROUP}: no entry_point named {name!r}")
        return eps[name]

    def all_names(self) -> list[str]:
        return sorted(self._discover().keys())

    def has(self, name: str) -> bool:
        return name in self._discover()

    def reset(self) -> None:
        """Testing helper: clear the cache (rediscover after monkeypatch)."""
        self._cache = None
