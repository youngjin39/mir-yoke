---
adr: 56
status: accepted
source: mirrored-summary
---

# ADR-56 — Symmetric Main-Agent Parity

## Context

The public template needs a stable reference record for ADR-56 so applied-state
verification can confirm the baseline catalog is complete.

## Decision

Whichever CLI is opened (Claude or Codex) is the control-plane main; the delegated
execution-backend ownership model is identical regardless of which CLI launched the
session. The template preserves a concise, English-only reference stub for this ADR
number; detailed execution history remains in the upstream control repository.

## Consequences

- The template keeps a stable ADR number map.
- Public consumers can verify baseline completeness.
- The position-bound parity mechanism (agent preambles, setup.sh ownership, code-path
  enforcement hooks) ships in the template; repository-specific operational detail
  stays upstream.
