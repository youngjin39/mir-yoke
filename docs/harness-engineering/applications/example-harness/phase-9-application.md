---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical fleet catalog phase pointer
---

# Phase 9 — Fleet Catalog Application — Historical Pointer

This completed ledger recorded a private control-plane repository applying a fleet catalog phase to itself: a central fleet state file
and its schema treated as the single source of truth for per-repository adoption, a rendered catalog view, a drift detector, an opt-in
share catalog of innovations, and a daily refresh job scheduled on the maintainer's machine. That state file, its schema and every named
tool under `tools/fleet_observe/` are absent from this repository.

Current authority is ADR-83 (the four-file Starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption
layers), ADR-84, which already classifies this whole directory as history, ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this
repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are
cancelled and named only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in
[the archive](../../../_archive/harness-engineering/applications/example-harness/phase-9-application-2026-06-13-historical.md).
