---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical subagent worker isolation pointer
---

# Phase 5 — Subagents & Worker Isolation — Historical Pointer

This document restricted subagent delegation to work that could be safely isolated from the main flow, and specified the contract for doing so. It listed four qualifying conditions and three permitted roles (review, research, test), a handoff contract enumerating what to pass and what to withhold, a four-step worker-isolation flow across two model lanes (joint planning, code writing, first-pass verification, merge judgment), a per-case `fork_context` inheritance table, a default concurrent cap of four with spawn-failure degraded-mode rules, an author-is-not-verifier prohibition on self-evaluation, and a rule that subagents arrive only after a state machine is already running. Its application table pointed at a fifteen-plus agent registry, named executor and final-reviewer lanes, and a role policy held in a separate control repository.

That registry, those lanes, and that role policy do not exist in this repository, and per-family agent-count tracking and cross-family agent reuse catalogs were never built. The current authority is ADR-83 (product boundary — the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/phase-5-subagents-2026-06-13-historical.md).
