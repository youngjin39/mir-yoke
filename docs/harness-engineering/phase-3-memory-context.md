---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical memory and context contract pointer
---

# Phase 3 — Memory & Context — Historical Pointer

This document bound memory, documentation, and reading order to a single source of truth and specified what may be injected into a prompt. It defined a source-of-truth separation table with a "map is not territory" rule, an eight-layer context priority model, upfront versus on-demand injection rules plus a cross-source deduplication requirement enforced at insert time, a `memory_entry` lifetime schema (status, supersession pointer, validity date, source-of-truth tag) with four automatic expiry triggers that it recorded as not yet implemented, contamination signals, cache-stability rules, `/compact` thresholds, a sliding-window N table keyed by task subtype, and instruction-file writing principles with an import-splitting convention. Its application table cited a memory entry schema, a store module, a session-start hook, an upfront-context builder script, and a context measurement module under a fleet observation toolkit.

Those schemas, stores, hooks, and measurement modules are absent from this repository, and the fleet-wide memory monitoring it described was never built. The current authority is ADR-83 (product boundary — the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter); the Project Agent Kit's own bounded SQLite memory is the only memory surface this repository ships. Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/phase-3-memory-context-2026-06-13-historical.md).
