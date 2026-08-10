---
title: ADR-80 Release Runtime Isolation and Adopter Ownership
status: accepted
date: 2026-08-10
---

# ADR-80: Release Runtime Isolation and Adopter Ownership

## Context

Mir Yoke is an agent-guided starter, but its release path still allowed two independent projects to
share one `uv tool` environment, installed a dirty checkout instead of a committed source, retained
a provider-only validator in one adopter profile, depended on non-portable `flock`, and could issue a
ready receipt while a Git remote still pushed to the Mir Yoke provider repository.

The release must stay simple: the agent applies the baseline to the current repository, adapted
reference files remain product-owned, and Mir Yoke never commits, pushes, or rewrites product Git
history automatically.

## Decision

1. `setup.sh` derives a stable runtime identifier from the canonical project path and the locked
   provider URL and commit. `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR` live under that project-specific
   namespace, including when multiple projects share one external storage root.
2. Installation always uses the HTTPS URL and exact commit from the tracked
   `.mir/capability-lock.json`; it never installs the dirty working tree. Production dependencies are
   constrained by the tracked `config/cli-runtime-constraints.txt`, which must match `uv.lock`.
3. A valid receipt-bound executable may be reused without reinstalling. Reinstall or repair fails
   closed when the tracked source lock or constraints are unavailable or invalid. The receipt also
   binds a deterministic manifest of the installed runtime closure; setup and the startup gate
   reject changes to installed package files, executable modes, or symlink targets.
4. A product may enter bootstrap only when no effective Git push URL resolves to the Mir Yoke
   provider. The agent may rename a provider remote, disable its push URL, and optionally add a
   product-owned `origin`. Mir Yoke does not mutate remotes, commit, push, or rewrite history.
5. Modified `remove` references remain preserved as product-owned adaptations. Provider identity
   markers remain fail-closed. Provider-only validator source and generated mirrors are maintainer
   assets, never adopter payload or profile selections.
6. Retained starter automation uses platform-native primitives available on macOS, Linux, and WSL;
   the loop driver uses an atomic directory lock rather than `flock`.
7. Release proof remains commit-bound. The protected capability lock references the committed
   implementation tree, so implementation and lock refresh are separate commits.

## Consequences

- Separate projects cannot replace each other's Mir CLI runtime through a shared tool directory.
- The installed CLI source and dependency resolution are reproducible from tracked release data.
- A changed installed dependency cannot remain trusted merely because the launcher hash is stable.
- A ready product cannot accidentally push to the provider repository, while its inherited history
  remains available as provenance.
- Agent-guided adaptations are preserved unless they retain an explicit provider boundary marker.
- Release closure requires a two-commit sequence followed by the clean-tree release gate.

## Verification

- Two projects sharing storage receive different tool and bin directories.
- Dirty provider files do not affect the exact-commit install source.
- Bootstrap rejects provider push remotes before host or repository mutation and reports owner
  actions needed to continue.
- Adopter catalogs and materialized slim candidates contain no template-sync validator.
- The loop driver completes and excludes a concurrent second process without `flock`.
- The tracked dependency constraints equal a frozen production export of `uv.lock`.
- Runtime-manifest verification detects installed dependency and symlink drift.
