---
status: superseded
date: 2026-05-28
updated: 2026-09-02
scope: historical dispatch brief rollout pointer
---

# DispatchBrief Rollout Playbook (2026-05-28) — Historical Pointer

This playbook was a wave-by-wave procedure for pushing a task-triage contract into every managed repository: a three-size task
classification, per-repository-type brief defaults, an ordered rollout across a private control-plane repository, a private template
repository and a roster of private family repositories, an eight-step per-repository checklist, a privileged cross-repository write
channel, and a rollback keyed to `config/fleet-harness-state.json`. No such channel, state file or roster exists here.

Current authority is ADR-83 (the four-file Starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption
layers), ADR-84, which already classifies this whole directory as history, ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this
repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are
cancelled and named only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in
[the archive](../../_archive/harness-engineering/applications/dispatchbrief-rollout-playbook-2026-05-28-historical.md).
