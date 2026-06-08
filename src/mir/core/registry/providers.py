"""ProviderRegistry — `mir.providers` entry_points (MirProviderAdapter subclasses).

design §8.4 · V3 · v0.5.3 R7 allowlist gate.
"""
from __future__ import annotations

from typing import Any

from mir.core.contracts import GateBlocked

from .base import EntryPointRegistry


class ProviderRegistry(EntryPointRegistry):
    GROUP = "mir.providers"

    def create(
        self,
        name: str,
        cfg: Any,                          # ResolvedConfig (Any to avoid circular imports)
        **kwargs: Any,
    ) -> Any:
        """Create an instance after the allowlist gate and sync contract verification.
        Phase 1 Step 1 skeleton: reject all providers when the allowlist is empty.
        """
        cls = self.get(name)

        allowed = getattr(cfg.providers, "allowlist", {}) or {}
        if name not in allowed:
            raise GateBlocked(
                "provider_not_allowed",
                f"{name!r} not in harness_a.toml [providers.allowlist]",
            )

        # v0.5.3 V3: every registered provider must be a MirProviderAdapter
        # subclass — the class that carries the Mir-only ``dispatch`` contract.
        # Import lazily so the registry module itself has no worker-tier dep
        # at import time (keeps Phase 1 Step 1 loadable without Step 4 code).
        from mir.core.worker.mir_provider_adapter import MirProviderAdapter
        if not (isinstance(cls, type) and issubclass(cls, MirProviderAdapter)):
            raise AssertionError(
                f"{name}: entry point must resolve to a MirProviderAdapter "
                "subclass (V3 contract)"
            )

        # Sync contract verification (O1).
        import inspect
        for method in ("dispatch", "initialize", "cleanup"):
            m = getattr(cls, method, None)
            if m is not None and inspect.iscoroutinefunction(m):
                raise AssertionError(
                    f"{name}.{method} must be sync (O1 provider contract)"
                )

        return cls(**kwargs)
