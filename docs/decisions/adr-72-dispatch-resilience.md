---
adr: 72
status: proposed
date: 2026-07-11
source: mirrored-summary
---

# ADR-72 — Dispatch Resilience

## Context

The public template needs a concise reference for bounded dispatch recovery and the
verification boundary between single-operator and team use.

## Decision

Dispatch resilience uses a deterministic run-state sweep: stale running jobs are reaped
from `started_at + timeout + grace`, and orphan dispatch worktrees are reaped when their
job is absent or no longer running. A user-triggered CLI is dry-run by default; apply mode
performs the bounded cleanup. The sweep is repeatable and does not introduce a new state
store, heartbeat scheme, or daemon.

Lightweight degraded mode is a documented design: if the delegated lane is unavailable,
the first attempt reports `BLOCKED | reason=lane-unavailable`, retries remain finite, and a
manual relay path records the resulting evidence. There is no alternate automatic executor.

For single-operator local use, pre-commit hooks, the TDD ledger, and the merge gate are
local evidence. Team or multi-contributor adoption requires a server-side authoritative
gate: a protected `main` branch, CI that reruns tests and lint server-side, and no direct
pushes to `main`.

## Consequences

- Recovery is explicit, bounded, and safe to inspect before mutation.
- Lane outages surface honestly instead of silently switching execution backends.
- Team use has a mandatory server-side gate prerequisite; local evidence alone is not
  authoritative.
