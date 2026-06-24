"""RenderTarget registry for CLI-scoped profile compiler artifacts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class RenderTarget:
    """A CLI render target and the artifact keys it owns."""

    cli: str
    artifact_keys: tuple[str, ...]
    renderer_ref: str | None = None
    derivation_hook: str | None = None
    verify_hook: str | None = None


_RENDER_TARGETS: dict[str, RenderTarget] = {
    "claude": RenderTarget("claude", ("A", "C", "D", "H", "I", "J", "K", "N")),
    "codex": RenderTarget(
        "codex",
        ("B", "E", "G", "L", "M"),
        renderer_ref="tools.profile_compiler.render.derivation_scripts",
        derivation_hook="scripts/generate_codex_derivatives.sh",
        verify_hook="scripts/verify_codex_sync.py",
    ),
}


def _normalize_cli(cli: str) -> str:
    normalized = cli.strip().lower()
    if not normalized:
        raise ValueError("RenderTarget CLI name must be non-empty")
    return normalized


def _dedupe_artifact_keys(artifact_keys: Iterable[str]) -> tuple[str, ...]:
    keys = tuple(dict.fromkeys(artifact_keys))
    if not keys:
        raise ValueError("RenderTarget artifact_keys must be non-empty")
    return keys


def list_render_targets() -> dict[str, RenderTarget]:
    """Return a shallow copy of the registered render targets."""

    return dict(_RENDER_TARGETS)


def list_render_target_names() -> tuple[str, ...]:
    """Return registered CLI target names in stable order."""

    return tuple(sorted(_RENDER_TARGETS))


def get_render_target(cli: str) -> RenderTarget:
    """Return one registered render target."""

    return _RENDER_TARGETS[_normalize_cli(cli)]


def artifact_keys_for_cli(cli_names: Iterable[str]) -> frozenset[str]:
    """Return the union of artifact keys for the selected CLI names."""

    keys: list[str] = []
    seen: set[str] = set()
    for cli in cli_names:
        for key in get_render_target(cli).artifact_keys:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    if not keys:
        raise ValueError("At least one RenderTarget CLI name is required")
    return frozenset(keys)


def register_render_target(
    cli: str,
    artifact_keys: Iterable[str],
    *,
    renderer_ref: str | None = None,
    derivation_hook: str | None = None,
    verify_hook: str | None = None,
) -> RenderTarget:
    """Register a new CLI render target."""

    normalized = _normalize_cli(cli)
    if normalized in _RENDER_TARGETS:
        raise ValueError(f"RenderTarget already registered: {normalized}")
    target = RenderTarget(
        normalized,
        _dedupe_artifact_keys(artifact_keys),
        renderer_ref=renderer_ref,
        derivation_hook=derivation_hook,
        verify_hook=verify_hook,
    )
    _RENDER_TARGETS[normalized] = target
    return target


def unregister_render_target(cli: str) -> None:
    """Remove a render target registered by a test or extension."""

    del _RENDER_TARGETS[_normalize_cli(cli)]
