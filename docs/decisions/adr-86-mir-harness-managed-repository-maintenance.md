---
adr: 86
title: "Mir Harness-managed repository maintenance"
type: template-adr
created: 2026-08-30
status: accepted
amended: 2026-09-06
template_scope: mir-yoke
related_adrs: ["adr-83", "adr-84", "adr-85"]
schema: docs/templates/_schema/adr.schema.json
---

# ADR-86 — Mir Harness-Managed Repository Maintenance

## 2026-09-06 Purpose and Management Amendment

This amendment controls where it conflicts with earlier template-only characterizations of Yoke's
primary role. Mir Yoke is the **Harness-managed central capability supply system for independently
owned repositories**. Its public-template classification describes a distribution form, not its
primary purpose or a transfer of consumer authority.

Mir Harness owns management direction, reuse decisions, verification, and authorized delivery
coordination. Yoke owns generic shared capability sources, plugins, separately distributed common
agents and commands, versioned delivery, and compatibility evidence. Consumers retain their goals,
data, local policy, adapters, and execution.

ADR-78, ADR-83, and ADR-84 continue to own their identity, adoption-layer, and upgrade-guidance
boundaries. This amendment takes precedence only for Yoke's primary purpose and the Harness/Yoke/
consumer management relationship. It neither creates a running service or control plane nor changes
the supported Starter, Project Agent Kit, optional CLI, or optional-plugin interfaces.

## Decision

Mir Harness is the designated repository-maintenance manager for Mir Yoke. It may inspect and
directly modify Yoke from this Git root without a target-prompt handoff, per-file approval, or a
second protected-path approval. The manager must follow this repository's instructions and Profile,
preserve unrelated dirty work, edit canonical sources before generated derivatives, and run Yoke's
own verification.

`.mir/capability-lock.json` is commit-bound managed configuration, not a protected path in the
Mir Yoke maintainer Profile. It may be reconciled to a committed implementation without a separate
protected-path approval, but its exact committed-object regression remains mandatory.

This maintenance role does not make Mir Yoke an agent runtime or give it authority over consumer
repositories. Adopter-generated Profiles keep their own capability locks protected. Commit, push,
tag, release, destructive operations, credentials, and consumer-repository changes continue to
require current explicit user authority.
