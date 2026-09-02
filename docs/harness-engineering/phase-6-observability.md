---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical observability metrics rollup pointer
---

# Phase 6 — Observability & Auto-correction — Historical Pointer

This document made measurement the precondition for improvement and specified twelve metrics as its single source of truth — context size, tool calls, repeated reads, giant outputs, subagent spawns, compaction timing, retry patterns, cache hits, plus cost, latency, approval rate, and error rate — mapped onto a seven-axis measurement toolkit and onto OpenTelemetry GenAI semantic conventions. It also defined a measure/fix/automate cadence that migrated manual rules into hooks, an autonomous reply loop bounded by a retry budget and circuit breaker, five cost-waste patterns with remedies, a candidate tool comparison that rejected external observability vendors in favour of self-built measurement, a `report_contract` output schema, and a separate evaluation harness of golden dataset, scoring rubric, CI gate, and regression pool recorded as largely not yet implemented. Its axis modules and the planned cost and latency measurement modules lived under a fleet observation toolkit.

That toolkit, those measurement modules, and the fleet observability rollup that aggregated per-family axes into drift comparisons are absent from this repository. The current authority is ADR-83 (product boundary — the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/phase-6-observability-2026-06-13-historical.md).
