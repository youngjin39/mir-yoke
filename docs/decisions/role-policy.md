---
title: Claude Control / Codex Execution Role Policy
keywords: [claude, codex, role-policy, orchestration, tdd, review, override]
related: []
created: 2026-05-02
---

# Claude Control / Codex Execution Role Policy

## Decision

This harness uses a **biased dual-runtime policy**, not a symmetric one.

- Claude is the default control plane:
  - clarification
  - design
  - orchestration
  - planning
  - dispatch
  - exception handling
  - final acceptance judgment
- Codex is the default code plane:
  - code writing
  - code modification
  - composite TDD execution
  - deterministic pass/fail validation
  - code review

## Why

This matches the harness goal better than either:
- a Claude-first coding loop, or
- a fully symmetric runtime model.

Reasons:
- code/TDD/review should be pinned to a tool-first, verifier-heavy lane
- Claude remains stronger as the top-level planner and controller
- role separation reduces self-approval bias

## Override Policy

This harness distinguishes between a **runtime override** and a **project-level policy revision**.

### Runtime Override

Role swaps are allowed, but only conditionally for the active task or session.

Allowed triggers:
- explicit user request
- Codex unavailable
- Codex hits the configured failure limit
- task is docs-only or otherwise outside code execution scope

Required action:
- record the override and reason in `tasks/plan.md` or the active handoff note

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

- Do not make Claude and Codex interchangeable by default.
- Do not let "flexibility" erase default ownership.
- Do not treat a runtime override as if it were a policy revision.
- Do not treat review as a substitute for executed TDD evidence.

## Operational Consequence

The harness contract must say the same thing in all layers:
- `CLAUDE.md`
- `AGENTS.md`
- mandatory code-work skills
- agent role definitions
- regression tests

If one layer says Codex is optional for review or code execution, the contract is drifting.
