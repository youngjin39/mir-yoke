---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical fleet family classification pointer
---

# Phase 7 — Fleet Expansion & Classification — Historical Pointer

This document specified how a harness would be dogfooded on itself and then ported to N further repositories under differential strictness. It defined a six-type family classification keyed to artifact nature, failure risk, and gate strictness; an inheritance graph rooted in a shared type; a self-stop condition requiring the project to halt if enforcement failed against its own repository; a dogfooding order and a concurrent-versus-serial rollout decision table; a fleet rollout matrix drawing `family_type`, `repository_type`, `rollout_class`, and `status` from per-family JSON profiles, with a sealed-family policy; an eight-step porting procedure from survey through gate; a per-type strictness differential table; a cross-pollination sharing catalog; and a user-initiated public template sync requiring sanitization. It cited a fleet observation toolkit, a registry-entry bootstrap script, and a repository-agent-management verifier.

None of those profiles, verifiers, or rollout classes exist in this repository, and it has no standing authority over any consumer repository to classify or port. The current authority is ADR-83 (product boundary — the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/phase-7-fleet-expansion-2026-06-13-historical.md).
