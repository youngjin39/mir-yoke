---
adr: 72
status: accepted
date: 2026-07-11
amended: 2026-07-15
source: sanitized-template-summary
amended_by: [adr-73]
---

# ADR-72 — Dispatch Resilience

## Current Decision

Elapsed-time and inactivity observations are advisory. Age alone never marks a running job failed,
advances retries, or makes its worktree removable. Cleanup is limited to terminal jobs or explicit
operator action, is dry-run by default, and must never touch the main worktree.

A lane-local startup or handshake failure is recorded honestly but does not automatically block the
whole task. Main inspects the evidence once and may use a materially different safe direct, native,
MCP, or manual path when the repository contract permits it. There is no common retry count,
automatic cross-engine fallback, alternate auto-executor, or queue daemon.

For team or multi-contributor use, local hooks and ledgers are evidence rather than an authoritative
gate. Protect the main branch and rerun required tests and lint in server-side CI.
