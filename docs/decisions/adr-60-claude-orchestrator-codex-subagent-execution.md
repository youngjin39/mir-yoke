---
adr: 60
status: accepted
source: mirrored-summary
---

# ADR-60 — Claude-Orchestrator / MCP-Backed Codex Sub-Agent Execution

## Context

The public template needs a stable reference record for ADR-60 so applied-state
verification can confirm the baseline catalog is complete.

## Decision

The orchestration/execution split is codified: the opened main session is the orchestrator (control
plane — requirements, design, dispatch judgment, the cursor), and backend-capable sub-agent work
routes through Codex without direct Claude-model Agent-loop execution. ADR-69 amends the transport:
Claude→Codex uses MCP, in-repo code/TDD/review writes use MCP-backed `mir_executor --dispatch`, and
Codex→Codex breadth uses native `multi_agent_v1`. Raw `codex exec` is banned; a missing MCP/native
path is `BLOCKED`, never an exec fallback. Each mutating sub-agent run uses its own git worktree
(structural isolation: it works on a copy and cannot reach the shared control cursor) and reports a
structured result the orchestrator reads and merges only after verification. The cursor is main-only
(the delegated agent never edits it); each dispatch is monitored, with the orchestrator running a
health check after every dispatch. Detailed execution history remains in the upstream control
repository.

## Consequences

- The template keeps a stable ADR number map.
- Public consumers can verify baseline completeness.
- Sub-agent execution is token-conserving, isolated, and monitored; the control cursor stays
  main-owned; deterministic gates and human-in-the-loop control are preserved.
