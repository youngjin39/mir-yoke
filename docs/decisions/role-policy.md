---
title: Main-Agent Parity / Delegated Execution Role Policy
keywords: [claude, codex, role-policy, orchestration, tdd, review, override]
related: []
created: 2026-05-02
---

# Main-Agent Parity / Delegated Execution Role Policy

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
- Delegated sub-agents are the execution plane by default:
  - code writing
  - code modification
  - composite TDD execution
  - deterministic pass/fail validation
  - code review
  - targeted research and bounded verification
- Codex is the default backend for delegated backend-capable execution work unless an explicit override or capability constraint requires otherwise.

## Why

This matches the harness goal better than either:
- a main-agent contract that changes depending on whether Claude or Codex was opened first, or
- a fully symmetric runtime model that erases delegated execution boundaries.

Reasons:
- the user should get the same main-session harness behavior from Claude or Codex
- execution work should stay pinned to delegated, verifier-heavy lanes
- Codex remains the preferred backend for delegated code-heavy loops
- delegated separation reduces self-approval bias without forcing main-agent asymmetry

## Override Policy

This harness distinguishes between a **runtime override** and a **project-level policy revision**.

### Runtime Override

Role overrides are allowed, but only conditionally for the active task or session.

Allowed triggers:
- explicit user request
- delegated Codex execution unavailable
- delegated Codex execution hits the configured failure limit
- task is docs-only or otherwise outside delegated execution scope

Required action:
- record the override and reason in `tasks/plan.md` or the active handoff note
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
- Do not let "flexibility" erase Codex-first delegated backend defaults without an explicit reason.
- Do not treat a runtime override as if it were a policy revision.
- Do not treat review as a substitute for executed TDD evidence.

## Operational Consequence

The harness contract must say the same thing in all layers:
- `CLAUDE.md`
- `AGENTS.md`
- mandatory code-work skills
- agent role definitions
- regression tests

If one layer says the main agent differs by runtime or removes Codex-first delegated execution without an explicit exception, the contract is drifting.
