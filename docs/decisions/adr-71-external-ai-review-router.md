---
adr: 71
status: accepted
date: 2026-07-11
amended: 2026-07-15
source: sanitized-template-summary
amended_by: [adr-73]
---

# ADR-71 — Optional External AI Review Contract

## Current Decision

External review is an optional, advisory source of untrusted material. Use it only when its expected
decision value exceeds coordination, privacy, and token cost. It never auto-fires, auto-applies a
result, or replaces internal verification and Main judgment.

Outbound material must pass deterministic secret, path, size, and binary checks. The public
template ships only the portable record schema and example policy. It does not ship private fleet
state, authenticated browser automation, repository-specific review history, or the reference
harness implementation.

## ADR-73 Precedence

Routine bounded work does not require external review. Any adopted recommendation must still pass
the repository's source-of-truth, safety, and verification boundaries.
