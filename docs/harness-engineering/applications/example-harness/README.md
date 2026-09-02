---
status: superseded
date: 2026-05-22
updated: 2026-09-02
scope: historical self-dogfooding rollout ledger pointer
---

# Self-Dogfooding Ledger — Phase 0-12 Rollout, Phase 13 Closure, Phase 14 Completion Consistency — Historical Pointer

This ledger recorded a private control-plane repository applying phases 0 through 14 to itself: a dependency flow, a per-phase status
table that reached `done` on every row, a status-code mapping onto a central fleet state file and a share-blocking verifier, a historical
priority ordering, an automated four-check promotion gate, and a rule that no external target could take a phase as enforced until the
self row passed. `verify_self_stop.py`, that state file and the per-repository rows it scored are absent from this repository.

Current authority is ADR-83 (the four-file Starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption
layers), ADR-84, which already classifies this whole directory as history, ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this
repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are
cancelled and named only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in
[the archive](../../../_archive/harness-engineering/applications/example-harness/README-2026-05-22-historical.md).
