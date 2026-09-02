---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical state machine phase pointer
---

# Phase 4 — State Machine Application — Historical Pointer

This completed ledger recorded a private control-plane repository applying a thirteen-state run state machine to itself, with five JSON
schemas, mandatory tool-contract fields enforced before any act step, structured errors, a stash-based interrupt and rollback path,
five-tier execution identifiers, and an approval object whose confirmation was delegated to an external chat channel. The orchestrator,
the engine modules, the schemas and that approval channel are all absent from this repository.

Current authority is ADR-83 (the four-file Starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption
layers), ADR-84, which already classifies this whole directory as history, ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this
repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are
cancelled and named only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in
[the archive](../../../_archive/harness-engineering/applications/example-harness/phase-4-application-2026-06-13-historical.md).
