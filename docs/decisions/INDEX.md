---
title: Public Harness Decision Index
status: accepted
updated: 2026-07-15
---

# Public Harness Decision Index

## Effective Precedence

Use the narrowest current decision that applies. When an older decision conflicts with a later
amendment, the later decision controls and the older text remains historical evidence only.

1. [ADR-73](adr-73-proportional-guidance-first-harness.md) governs proportional direct work,
   delegation, review, monitoring, and verification.
2. [ADR-69](adr-69-codex-exec-ban-mcp-only.md) retains the narrow raw-`codex exec` ban.
3. [ADR-72](adr-72-dispatch-resilience.md) governs terminal-only cleanup, lane-local failure, and
   the team CI boundary.
4. [ADR-60](adr-60-claude-orchestrator-codex-subagent-execution.md) and
   [ADR-65](adr-65-sub-agent-routing-sandbox.md) govern optional isolated delegation when selected.
5. [ADR-59](adr-59-agent-execution-monitoring.md) keeps monitoring observe-only.
6. [ADR-54](adr-54-template-anchored-fleet-parity-manifest-2026-06-06.md) keeps parity read-only and
   ownership-aware.
The [role policy](role-policy.md) binds Claude Main and Codex Main to the same control-plane
contract. Repository profiles and preserve rules narrow these portable defaults for each adopter.

## Public Boundary

This index lists the portable current contract. Detailed private rollout history, fleet inventories,
family paths, and operator records remain in the private reference harness and are not public
template inputs.
