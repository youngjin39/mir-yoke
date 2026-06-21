---
adr: 59
status: accepted
source: mirrored-summary
---

# ADR-59 — Agent-Execution Monitoring (main + sub-agents, observe-only)

## Context

The public template needs a stable reference record for ADR-59 so applied-state
verification can confirm the baseline catalog is complete.

## Decision

A read-only monitoring structure makes BOTH the main agent and every sub-agent (especially
delegated code-execution subprocesses) observable, closing recording gaps where a directly-spawned
execution subprocess and sub-agent transcripts escape existing records. Three reuse-first layers,
all observe-only: (L1) a single execution-binary shim emits a bounded lifecycle event
(start/exit/signal/duration) for every invocation — the minimal slice of event-sourcing for
monitoring, not a full event-sourcing engine; (L2) a unified health monitor over the lifecycle log,
the job registry, and main+sub transcripts, detecting hangs, stalls, repeated-error spinning, and
duration anomalies; (L2b) deterministic evidence-integrity checks the control-plane agent runs after
a dispatch (e.g. a narrowed lint-selection gate, executor edits to a prior committed ledger or the
control cursor); (L3) an agent-runnable check surface (scan/doctor) — the agent inspects health; a
human need not watch. All layers are advisory and surface to the control-plane agent, which decides;
no autonomous monitor-evolve loop, no auto-intervention. Detailed execution history remains in the
upstream control repository.

## Consequences

- The template keeps a stable ADR number map.
- Public consumers can verify baseline completeness.
- Monitoring is observe-only and agent-checked; deterministic gates remain the sole hard blockers,
  preserving the human-in-the-loop, no-fabricated-continuation model.
