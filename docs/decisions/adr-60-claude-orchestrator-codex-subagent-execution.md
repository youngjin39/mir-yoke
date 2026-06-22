---
adr: 60
status: accepted
source: mirrored-summary
---

# ADR-60 — Claude-Orchestrator / Codex-Subprocess Sub-Agent Execution

## Context

The public template needs a stable reference record for ADR-60 so applied-state
verification can confirm the baseline catalog is complete.

## Decision

The orchestration/execution split is codified: Claude is the orchestrator (control plane —
requirements, design, dispatch judgment, the cursor), and ALL sub-agent work (execution and review)
runs as `codex exec` subprocesses, never as Claude-model Agent-loop sub-agents — conserving Claude
tokens and sidestepping Anthropic-API overload for sub-agent work. Each sub-agent runs in its own git
worktree (structural isolation: it works on a copy and cannot reach the shared control cursor) and
reports a structured result the orchestrator reads and merges only after verification. A finite
resilience fallback to a Claude sub-agent applies after repeated codex failure for a single task; a
broader codex outage halts and alerts rather than mass-falling-back. The cursor is main-only (the
delegated agent never edits it); each subprocess is monitored, with the orchestrator running a health
check after every dispatch. Detailed execution history remains in the upstream control repository.

## Consequences

- The template keeps a stable ADR number map.
- Public consumers can verify baseline completeness.
- Sub-agent execution is token-conserving, isolated, and monitored; the control cursor stays
  main-owned; deterministic gates and human-in-the-loop control are preserved.
