---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical hook enforcement bindings pointer
---

# Phase 2 — Enforcement — Historical Pointer

This document specified four code-level enforcement bindings — a pre-edit hook, a post-edit verify hook, a static validator script, and a deny-list — on the principle that rules which matter must block rather than merely advise. Around them it defined nine prompt-injection regex patterns with a per-surface enforcement table (external fetches, borrowed code, and tool-server responses enforced; direct user input and one user-command channel exempt), a three-stage warn/suggest/block escalation with dangerous commands starting at block, a four-counter retry-budget circuit breaker, an author-versus-verifier lane split that blocked one model's direct writes to `src/` and `tools/`, a seven-point safety-layer model of which only two points were claimed, and an enforced-versus-advisory domain boundary. Its application table cited hook scripts under `.claude/hooks/`, a pre-commit verification script, TDD ledger guards, and an `.ai-harness/deny-list.yaml`.

None of those hooks, ledgers, guard scripts, or deny-list files exist in this repository, so the document describes an enforcement surface that cannot fire. The current authority is ADR-83 (product boundary — the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/phase-2-enforcement-2026-06-13-historical.md).
