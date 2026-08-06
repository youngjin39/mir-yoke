"""CLI entry points — `python -m mir …` dispatcher.

The public template exposes memory, bootstrap, capability, policy, and loop
operations through this registry.

Subcommand registration is the only job here; real work lives under each
subcommand module.
"""
from __future__ import annotations

from collections.abc import Callable

from . import bootstrap as _bootstrap
from . import capability as _capability
from . import context as _context
from . import loop as _loop
from . import memory as _memory
from . import migrate as _migrate
from . import policy as _policy

# Registry pattern (design §0): no hard-coded ladder in __main__.
# New subcommand = 1 row here.
SUBCOMMANDS: dict[str, Callable[[list[str]], int]] = {
    "bootstrap": _bootstrap.main,
    "capability": _capability.main,
    "context": _context.main,
    "loop": _loop.main,
    "memory": _memory.main,
    "migrate": _migrate.main,
    "policy": _policy.main,
}
