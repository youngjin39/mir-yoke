---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical start-harness phase ledger pointer
---

# Phase 1 — Start Harness Application — Historical Pointer

This completed ledger recorded a private control-plane repository applying a start-harness phase to itself: a mandatory five-element
task declaration, a risk-level taxonomy, routing-failure detection, and a warn-then-suggest-then-block rollout of the hooks that enforced
them, with per-repository-type propagation rules and a hook regression count as evidence. Those hooks were later archived in the source
repository, and neither they nor the blueprint they implemented exist here.

Current authority is ADR-83 (the four-file Starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption
layers), ADR-84, which already classifies this whole directory as history, ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this
repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are
cancelled and named only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in
[the archive](../../../_archive/harness-engineering/applications/example-harness/phase-1-application-2026-06-13-historical.md).
