---
adr: 86
title: "Mir Harness-managed repository maintenance"
type: template-adr
created: 2026-08-30
status: accepted
template_scope: mir-yoke
related_adrs: ["adr-83", "adr-84", "adr-85"]
schema: docs/templates/_schema/adr.schema.json
---

# ADR-86 — Mir Harness-Managed Repository Maintenance

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
