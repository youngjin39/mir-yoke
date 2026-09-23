---
title: Public Harness Decision Index
status: accepted
updated: 2026-09-24
---

# Public Harness Decision Index

Mir Yoke is the Harness-managed central capability supply system for independently owned
repositories. Its public template, standard agent-guided Project Agent Kit, optional installed CLI,
plugin provider, and reference corpus are distribution surfaces. It has no provider runtime, is not
an agent runtime, has no standing authority over consumer repositories, and is not a universal
installer. `starter/` remains the only fixed consumer payload.

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
5. [ADR-86](adr-86-mir-harness-managed-repository-maintenance.md) defines the current
   Harness-managed central-supply purpose, responsibility split, and consumer/release authority
   boundaries; its 2026-09-06 amendment takes precedence over older template-only role language.
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

## Complete decision register

This register lists every local ADR file and its recorded status. The current-authority order
above governs precedence; an older accepted record does not expand the supported surfaces.
Mirrored successor mappings below were verified against the archived Mir Harness
`superseded_by` fields under the owner authority recorded in `tasks/change_log.md`,
"Owner Tasks B and D (2026-09-24)". Mir Harness ADR numbers refer to that repository;
Mir Yoke decisions with the same numbers are different records.

| Record | Recorded status | Successor or retirement note |
|---|---|---|
| [ADR-01](adr-01-external-store.md) | accepted | — |
| [ADR-02](adr-02-skill-preserve-manifest.md) | accepted | — |
| [ADR-03](adr-03-phase-gate-policy.md) | accepted | — |
| [ADR-04](adr-04-claude-md-preserve.md) | accepted | — |
| [ADR-05](adr-05-mir-self-llmwiki.md) | superseded | Mir Harness ADR-50 |
| [ADR-06](adr-06-stall-detection-2026-05-11.md) | superseded | Mir Harness ADR-59 (the source note also names Mir Harness ADR-72 and Mir Harness ADR-73) |
| [ADR-07](adr-07-review-gate-2026-05-11.md) | superseded | Mir Harness ADR-73 |
| [ADR-08](adr-08-agent-routing-2026-05-12.md) | rejected | — |
| [ADR-09](adr-09-execution-backend-frontmatter.md) | accepted | — |
| [ADR-10](adr-10-fleet-governance-advisory-2026-05-18.md) | archived | — |
| [ADR-11](adr-11-fleet-inventory-catalog-axis-extension-2026-05-19.md) | accepted | — |
| [ADR-12](adr-12-prompt-cache-reshape-lane-2026-05-19.md) | superseded | Mir Harness ADR-74 |
| [ADR-13](adr-13-harness-generator-bootstrap-2026-05-19.md) | accepted | — |
| [ADR-14](adr-14-sqlite-memory-python-native-2026-05-19.md) | accepted | — |
| [ADR-15](adr-15-catalog-multi-agent-skill.md) | accepted | — |
| [ADR-16](adr-16-specialist-deployment-2026-05-21.md) | superseded | Mir Harness ADR-76 |
| [ADR-17](adr-17-orchestrator-context-routing-2026-05-21.md) | accepted | — |
| [ADR-18](adr-18-orchestrator-runtime-guard.md) | accepted | — |
| [ADR-19](adr-19-workflow-preset-json-encoding-2026-05-22.md) | deferred | — |
| [ADR-20](adr-20-per-family-execution-backend-schema-2026-05-22.md) | deferred | — |
| [ADR-21](adr-21-family-type-schema-2026-05-23.md) | accepted | — |
| [ADR-22](adr-22-sealed-family-policy-2026-05-23.md) | accepted | — |
| [ADR-23](adr-23-active-family-dogfooding-exception-2026-05-23.md) | superseded | Mir Harness ADR-41 (itself superseded by Mir Harness ADR-76) |
| [ADR-25](adr-25-fleet-catalog-2026-05-23.md) | archived | — |
| [ADR-26](adr-26-rollout-share-pipeline-2026-05-23.md) | superseded | Mir Harness ADR-76 |
| [ADR-27](adr-27-back-propagation-2026-05-23.md) | superseded | Mir Harness ADR-76 |
| [ADR-33](adr-33-design-complete-gate-hook-2026-05-23.md) | archived | — |
| [ADR-39](adr-39-template-applied-state-charter-2026-05-23.md) | accepted | — |
| [ADR-40](adr-40-mir-template-maintainer-charter-2026-05-23.md) | superseded | Mir Harness ADR-76 |
| [ADR-41](adr-41-verify-self-stop-hook-2026-05-23.md) | superseded | Mir Harness ADR-76 |
| [ADR-42](adr-42-verify-template-applied-state-2026-05-23.md) | superseded | Mir Harness ADR-76 |
| [ADR-43](adr-43-fleet-phase-4-rollout-deferral-2026-05-24.md) | superseded | Mir Harness ADR-44 |
| [ADR-44](adr-44-13-state-sm-migration-2026-05-24.md) | accepted | — |
| [ADR-45](adr-45-error-taxonomy-unification-2026-05-24.md) | accepted | — |
| [ADR-46](adr-46-phase-4-enforce-flip-rollout-2026-05-24.md) | accepted | — |
| [ADR-47](adr-47-orchestration-dispatch-brief-and-tiered-gates-2026-05-28.md) | accepted | — |
| [ADR-48](adr-48-central-fleet-management-and-direct-apply-2026-05-28.md) | archived | — |
| [ADR-49](adr-49-opus-4-8-alignment-and-model-tier-routing-2026-05-30.md) | accepted | — |
| [ADR-50](adr-50-memory-db-canonical-md-projection-2026-05-31.md) | accepted | — |
| [ADR-51](adr-51-harness-self-consistency-verification-2026-06-04.md) | accepted | — |
| [ADR-52](adr-52-fleet-admin-elevation-and-cross-repo-write-model-2026-06-05.md) | superseded | Mir Harness ADR-76 |
| [ADR-53](adr-53-context-assembly-current-only-retrieval-2026-06-05.md) | accepted | — |
| [ADR-54](adr-54-template-anchored-fleet-parity-manifest-2026-06-06.md) | archived | — |
| [ADR-55](adr-55-native-memory-db-projection-2026-06-08.md) | accepted | — |
| [ADR-56](adr-56-symmetric-main-parity.md) | accepted | — |
| [ADR-57](adr-57-callgraph-mcp-borrow-scaffold.md) | accepted | — |
| [ADR-58](adr-58-ouroboros-borrow-adoption.md) | accepted | — |
| [ADR-59](adr-59-agent-execution-monitoring.md) | accepted | — |
| [ADR-60](adr-60-claude-orchestrator-codex-subagent-execution.md) | accepted | — |
| [ADR-61](adr-61-cli-agnostic-meta-harness.md) | accepted | — |
| [ADR-65](adr-65-sub-agent-routing-sandbox.md) | accepted | — |
| [ADR-69](adr-69-codex-exec-ban-mcp-only.md) | accepted | — |
| [ADR-72](adr-72-dispatch-resilience.md) | accepted | — |
| [ADR-73](adr-73-proportional-guidance-first-harness.md) | accepted | — |
| [ADR-74](adr-74-portable-bootstrap-capability-sources-and-memory.md) | accepted | — |
| [ADR-75](adr-75-global-plugin-migration-gate.md) | accepted | — |
| [ADR-76](adr-76-codex-required-plugin-activation.md) | accepted | — |
| [ADR-77](adr-77-existing-repository-bootstrap-adoption.md) | accepted | — |
| [ADR-78](adr-78-public-template-identity-and-non-authority.md) | accepted | — |
| [ADR-79](adr-79-agent-guided-platform-scope.md) | accepted | — |
| [ADR-80](adr-80-release-runtime-isolation-and-adopter-ownership.md) | accepted | — |
| [ADR-81](adr-81-minimal-starter-support-boundary.md) | accepted | — |
| [ADR-82](adr-82-product-planes-capability-packs-and-composition.md) | superseded | [ADR-83](adr-83-project-agent-kit-recipe-and-supported-surfaces.md) |
| [ADR-83](adr-83-project-agent-kit-recipe-and-supported-surfaces.md) | accepted | — |
| [ADR-84](adr-84-harness-upgrade-guidance-and-runtime-hygiene.md) | accepted | — |
| [ADR-85](adr-85-global-policy-inheritance-and-agent-contracts.md) | accepted | — |
| [ADR-86](adr-86-mir-harness-managed-repository-maintenance.md) | accepted | — |
| [ADR-87](adr-87-deny-list-enforcement-recovery.md) | accepted | — |
| [ADR-88](adr-88-active-plugin-component-admission.md) | accepted | — |
| [ADR-89](adr-89-dual-runtime-capability-management.md) | accepted | — |
| [ADR-90](adr-90-role-plugins-and-common-hooks.md) | accepted | — |
