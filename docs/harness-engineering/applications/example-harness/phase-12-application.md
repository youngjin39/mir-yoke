---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical template lifecycle phase pointer
---

# Phase 12 — Template Lifecycle Application — Historical Pointer

This completed ledger recorded a private control-plane repository applying a template lifecycle phase to itself: four lifecycle stages
from create to sunset, a version-lag detector over per-repository adopted versions, patch, minor and major upgrade migration runbooks, a
hand-off protocol, and template continuous integration, tests and migration notes confirmed by an applied-state verifier.
`template_health.py`, `verify_template_applied_state.py` and `verify_self_stop.py` are absent from this repository.

Current authority is ADR-83 (the four-file Starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption
layers), ADR-84, which already classifies this whole directory as history, ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this
repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are
cancelled and named only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in
[the archive](../../../_archive/harness-engineering/applications/example-harness/phase-12-application-2026-06-13-historical.md).
