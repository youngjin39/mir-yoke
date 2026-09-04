---
title: Public Harness Decision Index
status: accepted
updated: 2026-09-04
---

# Public Harness Decision Index

Mir Yoke is a public template, standard agent-guided Project Agent Kit, optional installed CLI and
plugin provider, and reference corpus. It has no provider runtime and no standing authority over
consumer repositories. It is not a universal installer. `starter/` remains the only fixed consumer
payload.

## Current Authority

1. [ADR-90](adr-90-role-plugins-and-common-hooks.md) makes role-oriented plugins the canonical
   package for common workflows, admits the exact read-only lifecycle hook package, preserves the
   target-adapter boundary, and records the absent MCP-server state.
2. [ADR-89](adr-89-dual-runtime-capability-management.md) makes Yoke the tracked manager for
   agents, plugin skills, project-local hooks, optional MCP configuration, and Claude commands with
   Codex skill equivalents while preserving runtime-native delivery and consumer ownership.
3. [ADR-88](adr-88-active-plugin-component-admission.md) keeps role plugins skills-only, admits one
   exact `skills-hooks` package, and requires separate packages, kind-specific validation, and fresh
   digest acknowledgement for every active component.
4. [ADR-87](adr-87-deny-list-enforcement-recovery.md) restores deny-list enforcement, makes the
   destructive-command guards position-independent and POSIX-portable, and requires a test that
   asserts the blocking reason rather than only the exit code.
5. [ADR-86](adr-86-mir-harness-managed-repository-maintenance.md) designates Mir Harness as this
   repository's maintenance manager while preserving consumer and release authority boundaries.
6. [ADR-85](adr-85-global-policy-inheritance-and-agent-contracts.md) defines operator-owned Codex
   policy inheritance, runtime-neutral agent contracts, source-driven read-only roles, and the
   cross-runtime model boundary.
7. [ADR-83](adr-83-project-agent-kit-recipe-and-supported-surfaces.md), including the 2026-08-11
   owner amendment, defines the Minimal Starter, standard Project Agent Kit, optional installed
   `mir` CLI, plugin, and inert-reference boundaries. It supersedes ADR-82.
8. [ADR-79](adr-79-agent-guided-platform-scope.md), including the 2026-09-04 owner amendment,
   makes macOS the primary operational lane, isolates Linux/WSL compatibility evidence, and makes
   native Windows an AI-guided reference-adaptation lane.
9. [ADR-84](adr-84-harness-upgrade-guidance-and-runtime-hygiene.md) defines current,
   reference-only harness upgrades and the context, memory, embedding, hook, and generated-runtime
   hygiene boundary.
10. [ADR-81](adr-81-minimal-starter-support-boundary.md) defines `starter/` as the only supported
   consumer payload and removes advanced machinery from minimum readiness.
11. [ADR-78](adr-78-public-template-identity-and-non-authority.md) defines public-template identity
   and repository-local authority.
12. [ADR-73](adr-73-proportional-guidance-first-harness.md) defines proportional local work,
   delegation, review, and verification.

The Project Agent Kit recipe is supported guidance, not a second fixed payload. It creates a
project-owned common harness and required memory without copying Mir CLI source. The installed CLI
is separately opt-in and gains authority only from the user's explicit target and operation.

ADR-74, ADR-77, and ADR-80 govern the restored optional v0.8-compatible CLI behavior under
ADR-83's authority boundary. ADR-82 remains superseded; its selected files are preserved as inert
advanced-composition references, not active `yoke` commands.

## Historical Decisions

Central rollout, target mutation, superseded composition experiments, back-propagation, fleet
catalog, template parity, watchdog, and deployment decisions are non-authoritative history. Start at
[`docs/history/centralization`](../history/centralization/README.md); Git history preserves removed
implementation details.
