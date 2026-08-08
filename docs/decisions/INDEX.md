---
title: Public Harness Decision Index
status: accepted
updated: 2026-08-08
---

# Public Harness Decision Index

Mir Yoke is a public template and reference repository. It has no provider runtime and no standing
authority over consumer repositories. Later, narrower decisions control when older prose conflicts.

## Current Authority

1. [ADR-78](adr-78-public-template-identity-and-non-authority.md) defines the product identity,
   non-authority boundary, asset classifications, and local-only adoption model.
2. [ADR-77](adr-77-existing-repository-bootstrap-adoption.md) defines preservation-first reference
   assessment and the receipt-only explicit apply path for an existing repository.
3. [ADR-76](adr-76-codex-required-plugin-activation.md) narrows local capability activation proof.
4. [ADR-75](adr-75-global-plugin-migration-gate.md) applies only to explicit local-host provider
   collision and discovery safety, as narrowed by ADR-78.
5. [ADR-74](adr-74-portable-bootstrap-capability-sources-and-memory.md) defines greenfield portable
   bootstrap and integrity-only capability provenance, as narrowed by ADR-78.
6. [ADR-73](adr-73-proportional-guidance-first-harness.md) defines proportional local work,
   delegation, review, and verification.

The [role policy](role-policy.md) is a consumer-side starter contract. A consumer owns its local
instructions and may change or remove that policy after adoption.

## Historical Decisions

Central rollout, back-propagation, direct-apply, fleet catalog, template parity, watchdog, and
deployment decisions are non-authoritative history. Start at
[`docs/history/centralization`](../history/centralization/README.md); the original ADR files remain
here so links and Git history stay intact.
