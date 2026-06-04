---
status: accepted
---

# ADR-48 — Central Fleet Management and Direct Apply

## Decision

The public template documents Mir as the central manager for active managed repositories and uses direct apply as the default rollout model, with explicit exception handling.

- Active managed repositories should receive minimum viable harness patches directly from the control repository.
- Public-template sync remains sanitized and user-directed.
- Sealed, suspended, or runtime-contract-exception repositories are not generic direct-apply targets.

## Why

This keeps the template aligned with the managed-fleet operating model without forcing unsafe bulk changes.

## Consequence

Template consumers inherit:
- a central-manager mental model
- explicit exception lanes
- rollout documentation that separates standard direct apply from advisory or track-only repositories
