---
adr: 73
status: accepted
date: 2026-07-13
source: sanitized-template-summary
---

# ADR-73 — Proportional, Guidance-First Harness

## Decision

The harness uses proportional guidance by default. Main may complete tiny or bounded work directly.
Design notes, delegation, worktrees, TDD ledgers, independent review, agent health checks, and full
suites are selected when their risk reduction is worth their cost; none is a universal entry gate
merely because a task changes development files.

For non-trivial changed behavior, run the smallest check that can fail for that behavior. Add broader
verification when the affected boundary, blast radius, or release context justifies it.

## Hard-Block Boundary

A hard block requires deterministic evidence such as unauthorized destructive work, credential or
privacy exposure, protected-scope or source-of-truth violation, unauthorized external mutation, a
real integration conflict, or failure of verification explicitly required for the change. Missing
optional metadata, elapsed time, agent counts, review counts, backend preference, and unrelated
working-tree dirtiness are not hard-block reasons.

Raw `codex exec` remains prohibited by ADR-69. A preferred delegated lane being unavailable degrades
that lane, not necessarily the task.

## Template Boundary

Mir Yoke carries this portable operating contract. Private fleet tooling, repository paths, family
state, authenticated private transports, and private historical records stay outside the public
template.
