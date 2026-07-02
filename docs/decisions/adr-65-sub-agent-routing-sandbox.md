---
adr: 65
status: accepted
source: mirrored-summary
---

# ADR-65 — Sub-Agent Routing and Codex Sandbox Policy

## Context

The public template needs a stable, generic routing record for Codex-backed sub-agent work. The
record must describe the operational contract without repository-specific paths, private deployment
names, or secrets.

## Decision

Sub-agent routing depends on which CLI owns the main control plane:

- Claude-main routes Codex sub-agent work through Codex MCP. Start with `mcp__codex__codex`; continue
  the same conversation with `codex-reply`.
- Codex-main routes Codex sub-agent work through native `multi_agent_v1`: `tool_search`,
  `spawn_agent`, `wait_agent`, then `close_agent`.
- In-repo code, TDD, and review work routes through `mir_executor --dispatch`, preserving dispatch
  worktrees, deterministic merge gates, and TDD evidence.
- Raw `codex exec` is a guarded exception only, used when the primary route is unavailable or
  inappropriate for a clearly recorded reason.

Codex MCP and mutating Codex lanes use `sandbox=danger-full-access`. `workspace-write` is forbidden
for those lanes. Read-only cases may still use `read-only`.

## Consequences

- Claude-main and Codex-main keep the same control-plane contract while using the routing surface
  native to each runtime.
- Mutating repository work keeps deterministic merge and verification gates.
- The public template carries only generic English policy text; private paths, deployment names, and
  secrets stay out of the template.
