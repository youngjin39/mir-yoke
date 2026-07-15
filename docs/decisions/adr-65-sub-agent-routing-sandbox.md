---
adr: 65
status: accepted
date: 2026-07-02
amended: 2026-07-15
source: sanitized-template-summary
amended_by: [adr-69, adr-73]
---

# ADR-65 — Delegated Routing and Sandbox Policy

## Current Decision

When delegation is selected:

- Claude Main uses the supported Codex MCP lane.
- Codex Main may use its native sub-agent lane.
- Isolated in-repository mutation may use MCP-backed `mir_executor --dispatch` when its worktree,
  allowlist, and merge evidence justify the coordination cost.
- Raw `codex exec` is prohibited by ADR-69.

Mutating Codex lanes use the approved sandbox and repository safety boundaries. Read-only work may
use a narrower sandbox when the active runtime supports it.

## ADR-73 Precedence

These are routing rules for delegated work, not a requirement to delegate every code change. An
unavailable preferred lane is a lane limitation; it blocks the task only when no safe in-scope path
remains.
