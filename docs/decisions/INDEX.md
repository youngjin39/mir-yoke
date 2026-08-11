---
title: Public Harness Decision Index
status: accepted
updated: 2026-08-11
---

# Public Harness Decision Index

Mir Yoke is a public template, supported agent-guided recipe, optional plugin provider, and
reference corpus. It has no provider runtime and no standing authority over consumer repositories.
It is not a universal installer. `starter/` remains the only supported consumer payload.

## Current Authority

1. [ADR-83](adr-83-project-agent-kit-recipe-and-supported-surfaces.md) defines the Starter,
   Project Agent Kit recipe, portable plugin provider, and reference corpus boundaries. It
   supersedes ADR-82.
2. [ADR-81](adr-81-minimal-starter-support-boundary.md) defines `starter/` as the only supported
   consumer payload and removes advanced machinery from minimum readiness.
3. [ADR-78](adr-78-public-template-identity-and-non-authority.md) defines public-template identity
   and repository-local authority.
4. [ADR-73](adr-73-proportional-guidance-first-harness.md) defines proportional local work,
   delegation, review, and verification.

The Project Agent Kit recipe is supported guidance, not a second payload. It authorizes no provider
write; the active target agent acts only under the current user's explicit target prompt.

ADR-74 through ADR-77, ADR-79, ADR-80, and ADR-82 describe retained or superseded bootstrap and
composition experiments. They remain retrievable evidence without current consumer authority.

## Historical Decisions

Central rollout, target mutation, superseded composition experiments, back-propagation, fleet
catalog, template parity, watchdog, and deployment decisions are non-authoritative history. Start at
[`docs/history/centralization`](../history/centralization/README.md); Git history preserves removed
implementation details.
