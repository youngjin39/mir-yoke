---
status: superseded
date: 2026-05-28
updated: 2026-09-02
scope: historical phase-12 baseline stub pointer
---

# Phase 12 — Template Lifecycle — Historical Pointer

This stub asserted that the public template carried the phase-12 versioning, migration and template-maintenance-responsibility artifacts a per-repository rollout profile required, deferred all repository-specific execution evidence to a separate control repository, and reported itself applied at template-baseline level for selective opt-in. Authority now sits with ADR-83 (the product boundary: the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter); fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and named only to forbid their return, and the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/phase-12-baseline-2026-05-28-historical.md).
