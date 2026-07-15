---
adr: 60
status: accepted
date: 2026-06-22
amended: 2026-07-15
source: sanitized-template-summary
amended_by: [adr-65, adr-69, adr-73]
---

# ADR-60 — Delegated Isolation and Main-Owned Integration

## Current Decision

Whichever supported CLI is opened is the control-plane Main. Main owns scope, any active plan
cursor, integration judgment, verification synthesis, and final communication.

When delegated mutation benefits from isolation or restartability, use the repository-approved
dispatch lane and a separate worktree. Accept delegated output only with deterministic changed-path
and relevant verification evidence. Job age and inactivity remain advisory and never authorize
automatic failure, retry, or worktree deletion.

## ADR-73 Precedence

Delegation, per-agent worktrees, health checks, and fixed retry sequences are not universal entry
gates. Bounded work may be completed directly by Main. A missing preferred lane does not block safe
direct, native, MCP, or manual work that remains within the repository contract.

Raw `codex exec` remains prohibited by ADR-69.
