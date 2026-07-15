---
title: Main-Agent Parity / Delegated Execution Role Policy
keywords: [claude, codex, role-policy, orchestration, tdd, review, override]
related: []
created: 2026-05-02
---

# Main-Agent Parity / Proportional Execution Role Policy

Amended 2026-07-13 by ADR-73 proportional guidance: delegation is a tool, not a universal
execution gate.

## Decision

This harness uses a **two-layer role policy**.

- Claude main and Codex main share the same main-agent contract:
  - clarification
  - design
  - orchestration
  - planning
  - dispatch
  - exception handling
  - verification synthesis
  - final acceptance judgment
- The opened main may execute bounded work directly. Delegated sub-agents are preferred when
  isolation, parallelism, specialist context, independent review, or restartability materially
  helps.
- Codex is the preferred backend when delegated backend-capable work is selected, unless an
  explicit override or capability constraint requires otherwise.
- Design artifacts, TDD ledgers, review rounds, worktrees, agent-check, and full-suite verification
  are proportional tools rather than universal prerequisites.

## Why

This matches the harness goal better than either:
- a main-agent contract that changes depending on whether Claude or Codex was opened first, or
- a fully symmetric runtime model that erases delegated execution boundaries.

Reasons:
- the user should get the same main-session harness behavior from Claude or Codex
- bounded work should not pay for delegated or verifier-heavy lanes without a concrete benefit
- Codex remains the preferred backend for delegated code-heavy loops
- delegated separation can reduce self-approval bias for consequential work without forcing it on
  every edit

## Override Policy

This harness distinguishes between a **runtime override** and a **project-level policy revision**.

### Runtime Override

Choosing bounded direct-main work is not a role override. A runtime override is a material change to
the selected ownership model for a task that genuinely requires a protected or delegated lane.

Allowed triggers:
- explicit user request
- delegated Codex execution unavailable
- a task-specific protected route is unavailable
- the user explicitly changes ownership

Required action:
- record only a material override and its reason in `tasks/plan.md` or the active handoff note
- keep the shared main-agent contract intact unless the policy itself is being revised

Runtime overrides are:
- temporary
- local to the active task, session, or handoff
- not permission to silently rewrite the default role contract

### Project-Level Policy Revision

If CLI quality, token budget, stability, review quality, or TDD performance materially changes, the default ownership model may be revised at the project policy level.

Required action:
- update this decision document first
- update `CLAUDE.md` and regenerate `AGENTS.md` plus derivative mirrors
- update agent/skill wording when the ownership contract changes
- update regression tests so the new policy is pinned across all layers

Project-level policy revisions are:
- durable
- versioned
- meant to change future generated harness behavior, not just a single active session

## Non-Goals

- Do not make the main-agent contract depend on whether Claude or Codex was launched first.
- Do not make delegated sub-agents fully interchangeable across orchestration and execution ownership.
- Do not confuse a Codex-first delegated backend preference with mandatory delegation.
- Do not treat a runtime override as if it were a policy revision.
- Do not treat review as a substitute for relevant executed evidence.

## Operational Consequence

The harness contract must say the same thing in all layers:
- `CLAUDE.md`
- `AGENTS.md`
- relevant code-work skills
- agent role definitions
- regression tests

If one layer makes bounded direct work a universal block, or another weakens destructive,
credential, protected-scope, raw-Codex, or real-conflict boundaries, the contract is drifting.
