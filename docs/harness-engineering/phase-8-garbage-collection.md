---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical garbage collection cadence pointer
---

# Phase 8 — Automated Garbage Collection — Historical Pointer

This document specified automated detection and archival of unused, duplicate, and dead surfaces so that a harness would not accumulate weight over time. It named six detection domains (code, catalog, memory, documentation, hooks, stalled families), a seven-row cadence table running from per-commit linting to quarterly family re-evaluation, an archive lifecycle with concrete thresholds — thirty days unused, a seven-day contest grace period, and purge one hundred eighty days after archiving — a monthly instruction-file diet checklist, memory-lifetime cleanup keyed to the phase-3 lifetime schema and gated on it having landed first, catalog-consistency checks for zero-usage agents and skills, quarterly hook false-negative testing by injected violation, and an ADR active-versus-superseded lifecycle. It also claimed fleet GC orchestration in which one repository scheduled archive timing for the others.

The detector, catalog verifier, and cleanup subagents it cited are absent from this repository, and no repository here schedules garbage collection for another. The current authority is ADR-83 (product boundary — the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/phase-8-garbage-collection-2026-06-13-historical.md).
