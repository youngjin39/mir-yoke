---
adr: 58
status: accepted
source: mirrored-summary
---

# ADR-58 — Ouroboros Borrow Adoption (advisory-only, boundary-filtered extract)

## Context

The public template needs a stable reference record for ADR-58 so applied-state
verification can confirm the baseline catalog is complete.

## Decision

Six conflict-free features are borrowed from an external self-improving workflow
engine (ouroboros) as ADVISORY, boundary-compliant additions — never hard gates.
Every borrowed item passes a four-boundary acceptance filter: (A) hard blockers stay
deterministic hooks only, LLM judgment is never a gate; (B) dispatch and escalation
are control-plane-main owned, with no autonomous actuator; (C) the model-pin watchdog
is respected; (D) loop telemetry stays minimal with no second cursor. The adopted set:
an advisory consensus-verify panel (advocate / reused adversarial reviewer / judge,
recorded as an optional review-rounds field), a failure-class vocabulary plus recovery
taxonomy and a `set -o pipefail` evidence rule, an `llms.txt` condensed entrypoint, a
design-interview degraded-fallback brief, an `error_sig` telemetry field plus a
report-only SPINNING stagnation trigger, and a stagnation-to-persona affinity lookup.
The autonomous self-evolving loop, model escalation, and any LLM-as-hard-gate are
explicitly out of scope. Detailed execution history remains in the upstream control
repository.

## Consequences

- The template keeps a stable ADR number map.
- Public consumers can verify baseline completeness.
- All borrowed features are advisory; deterministic gates remain the sole hard
  blockers, preserving the human-in-the-loop, no-fabricated-continuation model.
