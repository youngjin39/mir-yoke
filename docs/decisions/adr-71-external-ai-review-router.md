---
adr: 71
status: proposed
date: 2026-07-11
source: mirrored-summary
---

# ADR-71 — External AI Review Router

## Context

The public template needs a concise, generic reference for an advisory external-review
lane without importing private operational history or implementation details.

## Decision

The proposed router follows a layered flow: internal check, memory recall, an advisory
need-judgment gate, external review, schema-validated result normalization, decision
merge with an untrusted-material posture, then archive and projection. The gate considers
nine criteria: multi-repository impact; unresolved internal disagreement; research beyond
current repository knowledge; high-impact prompt sensitivity; costly-to-reverse policy or
architecture; recurring unresolved problems; favorable cost of review; measurable
operational-quality risk; and unclear stakeholder-sensitive tradeoffs. It proposes review
only and never auto-fires.

The control-plane main owns orchestration and final judgment. The delegated code lane owns
code changes, TDD, deterministic verification, and in-repository review. External web
engines provide optional review or research through t1 browser transport or t2 human relay.
Their output is normalized into a schema-validated canonical database record; rendered
projections are derived from that record, never a second source of truth.

Outbound bundles are selective and fail closed: secret scanning, symlink-containment checks,
size and binary limits, plus a manifest and final hash are required before transport. No
credentials are stored, no login automation is performed, and external output is never
auto-applied; it remains untrusted material that must pass internal verification.

The template ships the record schema and an example policy configuration only. The router
implementation, including bundle/gate tooling and the capture CLI, lives in the reference
harness and is adopted separately.

## Consequences

- The template keeps a stable ADR number map and a portable record contract.
- External review remains advisory, traceable, and bounded by deterministic outbound checks.
- Public adopters choose and implement any router transport separately.
