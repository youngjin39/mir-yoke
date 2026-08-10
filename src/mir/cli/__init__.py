"""CLI entry points — `python -m mir …` dispatcher.

The public template exposes memory, bootstrap, existing-repository adoption,
capability, policy, and loop operations through this registry.

Subcommand registration is the only job here; real work lives under each
subcommand module.
"""
from __future__ import annotations

from collections.abc import Callable
from importlib import import_module

_SUBCOMMAND_MODULES = {
    "bootstrap": "mir.cli.bootstrap",
    "bootstrap-adoption": "mir.cli.bootstrap_adoption",
    "capability": "mir.cli.capability",
    "context": "mir.cli.context",
    "executor": "tools.mir_executor.cli",
    "loop": "mir.cli.loop",
    "memory": "mir.cli.memory",
    "migrate": "mir.cli.migrate",
    "policy": "mir.cli.policy",
    "run-python": "mir.cli.run_python",
    "runtime-manifest": "mir.cli.runtime_manifest",
    "yoke": "mir.cli.yoke",
}


def _lazy_handler(module_name: str) -> Callable[[list[str]], int]:
    def run(argv: list[str]) -> int:
        module = import_module(module_name)
        return module.main(argv)

    return run


SUBCOMMANDS: dict[str, Callable[[list[str]], int]] = {
    name: _lazy_handler(module_name)
    for name, module_name in _SUBCOMMAND_MODULES.items()
}
