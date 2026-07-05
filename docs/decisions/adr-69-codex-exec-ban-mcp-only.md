---
adr: 69
status: accepted
date: 2026-07-05
source: sanitized-template-summary
---

# ADR-69 — Codex Exec Ban: MCP-Only Delegation

## Context

ADR-65 allowed raw `codex exec` as a recorded exception. ADR-66 and ADR-67 moved the in-repository
Codex backend to MCP while preserving worktree isolation, allowlists, verification, and merge gates.
The remaining policy gap was the continued existence of raw exec as a fallback path.

## Decision

- Raw `codex exec` is banned in all forms.
- Claude→Codex delegation uses MCP only: `mcp__codex__codex` or
  `tools/mir_executor/codex_mcp_client.py`.
- In-repo code, TDD, and review writes use `mir_executor … --dispatch` with the MCP backend.
- Codex→Codex breadth uses native `multi_agent_v1`.
- Missing MCP/native routing means `BLOCKED`, never an exec fallback.
- The generated raw-exec launcher artifact is removed from the public template.

## Consequences

- Raw-exec timeout, stdin, and perl-alarm guards are obsolete as delegation guidance.
- Missing MCP provisioning must be fixed directly instead of bypassed.
- The public template keeps only sanitized, generic routing instructions.
