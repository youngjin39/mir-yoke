---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical subagent isolation phase pointer
---

# Phase 5 — Subagents Application — Historical Pointer

This completed ledger recorded a private control-plane repository applying a subagents phase to itself: an allowed role set with named
extensions, per-agent handoff contracts, a four-step worker isolation split in which one lane wrote and a different lane verified, a
fork-context policy, a default concurrency cap of four raisable to six, and self-assessment avoidance. The agent definition files, the
role policy record and the measurement logs it cites do not exist in this repository.

Current authority is ADR-83 (the four-file Starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption
layers), ADR-84, which already classifies this whole directory as history, ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this
repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are
cancelled and named only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in
[the archive](../../../_archive/harness-engineering/applications/example-harness/phase-5-application-2026-06-13-historical.md).
