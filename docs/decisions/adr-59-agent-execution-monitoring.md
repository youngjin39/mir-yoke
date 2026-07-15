---
adr: 59
status: accepted
date: 2026-06-22
amended: 2026-07-15
source: sanitized-template-summary
amended_by: [adr-69, adr-72, adr-73]
---

# ADR-59 — Observe-Only Agent Execution Monitoring

## Current Decision

Agent execution remains inspectable through the evidence produced by the active lane: MCP or native
dispatch records, job state, transcripts, lifecycle events, changed paths, and verification output.
Monitoring is evidence for the control-plane Main, never an autonomous actuator or a second task
cursor.

Monitoring must not automatically kill, fail, retry, merge, delete worktrees, or classify the whole
task as blocked. Run an agent health check only when work is anomalous, consequential, long-running,
or needs independent acceptance evidence.

## Current Boundaries

- Raw `codex exec` is prohibited by ADR-69 and is not a monitoring transport.
- Elapsed time and inactivity are advisory under ADR-72 and ADR-73.
- A deterministic safety or explicitly required verification failure remains binding on its own
  merits.
