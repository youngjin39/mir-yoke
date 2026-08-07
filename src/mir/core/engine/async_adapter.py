"""Async ↔ sync boundary for provider dispatch — §8.5.

Engine runs an asyncio event loop; providers stay sync (O1) because CAO and
most Worker CLIs' process-spawn APIs are sync. ``run_provider`` is the ONLY
place the transition happens. Tests (``tests/test_provider_sync_contract``)
fail if anyone tries to make a provider method async.

Why a wrapper instead of letting callers call ``to_thread`` inline:
  - Single point for adding timeouts, metrics, or cancellation semantics
    later without touching every call site.
  - Discoverability — grep for ``run_provider`` = every provider invocation.
"""
from __future__ import annotations

import asyncio

from mir.core.worker.mir_provider_adapter import MirProviderAdapter

from mir.core.contracts.compiled_job import CompiledJob
from mir.core.contracts.provider_result import ProviderResult


async def run_provider(
    adapter: MirProviderAdapter, compiled: CompiledJob
) -> ProviderResult:
    """Call ``adapter.dispatch(compiled)`` on a worker thread so the
    gateway's event loop keeps moving while the Worker CLI blocks."""
    return await asyncio.to_thread(adapter.dispatch, compiled)
