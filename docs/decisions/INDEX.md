---
title: Public Harness Decision Index
status: accepted
updated: 2026-08-11
---

# Public Harness Decision Index

Mir Yoke is a public template, standard agent-guided Project Agent Kit, optional installed CLI and
plugin provider, and reference corpus. It has no provider runtime and no standing authority over
consumer repositories. It is not a universal installer. `starter/` remains the only fixed consumer
payload.

## Current Authority

1. [ADR-83](adr-83-project-agent-kit-recipe-and-supported-surfaces.md), including the 2026-08-11
   owner amendment, defines the Minimal Starter, standard Project Agent Kit, optional installed
   `mir` CLI, plugin, and inert-reference boundaries. It supersedes ADR-82.
2. [ADR-81](adr-81-minimal-starter-support-boundary.md) defines `starter/` as the only supported
   consumer payload and removes advanced machinery from minimum readiness.
3. [ADR-78](adr-78-public-template-identity-and-non-authority.md) defines public-template identity
   and repository-local authority.
4. [ADR-73](adr-73-proportional-guidance-first-harness.md) defines proportional local work,
   delegation, review, and verification.

The Project Agent Kit recipe is supported guidance, not a second fixed payload. It creates a
project-owned common harness and required memory without copying Mir CLI source. The installed CLI
is separately opt-in and gains authority only from the user's explicit target and operation.

ADR-74, ADR-77, ADR-79, and ADR-80 govern the restored optional v0.8-compatible CLI behavior under
ADR-83's authority boundary. ADR-82 remains superseded; its selected files are preserved as inert
advanced-composition references, not active `yoke` commands.

## Historical Decisions

Central rollout, target mutation, superseded composition experiments, back-propagation, fleet
catalog, template parity, watchdog, and deployment decisions are non-authoritative history. Start at
[`docs/history/centralization`](../history/centralization/README.md); Git history preserves removed
implementation details.
