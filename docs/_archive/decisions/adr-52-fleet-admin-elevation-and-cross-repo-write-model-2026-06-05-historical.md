---
adr: 52
status: accepted
source: mirrored-summary
---

# ADR-52 — Fleet-Admin Elevation and Cross-Repo Write Model

## Context

The public template needs a stable reference record for ADR-52 so applied-state verification can confirm the baseline catalog is complete.

## Decision

ADR-52 pins the cross-repository write model: editor tools stay confined to the active session root, and cross-repository writes occur through the shell channel with a recorded elevation and audit entry per write. The template preserves a concise, English-only reference stub for this ADR number. Detailed execution history remains in the mir-harness control repository.

## Consequences

- The template keeps a stable ADR number map.
- Public consumers can verify baseline completeness.
- Repository-specific operational detail stays in mir-harness.
