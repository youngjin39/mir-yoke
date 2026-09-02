---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical garbage collection phase pointer
---

# Phase 8 — Garbage Collection Application — Historical Pointer

This completed ledger recorded a private control-plane repository applying a garbage-collection phase to itself: a four-pillar sweep, a
monthly cadence with recorded logs, an active-to-unused-to-archived component lifecycle, an instruction-file diet, memory lifetime
cleanup that exempted entries marked critical, false-negative hook testing against synthetic deny-list cases, and decision-record
lifecycle frontmatter. The detectors, runners and cadence scripts it names are absent from this repository.

Current authority is ADR-83 (the four-file Starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption
layers), ADR-84, which already classifies this whole directory as history, ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this
repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are
cancelled and named only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in
[the archive](../../../_archive/harness-engineering/applications/example-harness/phase-8-application-2026-06-13-historical.md).
